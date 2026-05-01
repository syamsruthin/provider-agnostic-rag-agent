"""
Hybrid RAG Tool — ChromaDB Vector Search + BM25 Keyword Search + Reranker
==========================================================================
Indexes the policy markdown documents into ChromaDB (all-MiniLM-L6-v2)
and a BM25 index. At query time, retrieves from both, merges via
Reciprocal Rank Fusion (RRF), and returns the top relevant chunks.
"""

import hashlib
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from rank_bm25 import BM25Okapi

from backend.core.config import CHROMA_DIR, DOCS_DIR, EMBEDDING_MODEL


# ---------------------------------------------------------------------------
# Document chunking
# ---------------------------------------------------------------------------
def _chunk_document(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    Split document text into overlapping chunks by character count,
    respecting paragraph boundaries where possible.
    """
    # Split on double newlines (paragraph boundaries)
    paragraphs = re.split(r"\n\n+", text.strip())

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk = current_chunk + "\n\n" + para if current_chunk else para
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            # If a single paragraph exceeds chunk_size, split it further
            if len(para) > chunk_size:
                words = para.split()
                sub = ""
                for word in words:
                    if len(sub) + len(word) + 1 <= chunk_size:
                        sub = sub + " " + word if sub else word
                    else:
                        chunks.append(sub.strip())
                        # Overlap: take last `overlap` chars
                        sub = sub[-overlap:] + " " + word if overlap else word
                current_chunk = sub
            else:
                current_chunk = para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def _load_and_chunk_docs() -> list[dict]:
    """
    Load all markdown files from the docs directory and chunk them.
    Returns list of dicts with 'text', 'source', 'chunk_id'.
    """
    all_chunks = []
    for md_file in sorted(DOCS_DIR.glob("*.md")):
        content = md_file.read_text()
        chunks = _chunk_document(content)
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{md_file.name}:{i}:{chunk[:50]}".encode()).hexdigest()
            all_chunks.append({
                "text": chunk,
                "source": md_file.name,
                "chunk_id": chunk_id,
                "chunk_index": i,
            })
    return all_chunks


# ---------------------------------------------------------------------------
# ChromaDB indexing
# ---------------------------------------------------------------------------
_chroma_collection = None
_bm25_index = None
_bm25_chunks = None


def _get_chroma_collection(force_reindex: bool = False):
    """Get or create the ChromaDB collection, indexing docs if needed."""
    global _chroma_collection

    if _chroma_collection is not None and not force_reindex:
        return _chroma_collection

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection_name = "healthguard_policies"

    # Check if collection exists and has documents
    try:
        collection = client.get_collection(name=collection_name, embedding_function=ef)
        if collection.count() > 0 and not force_reindex:
            _chroma_collection = collection
            return _chroma_collection
        # If empty or reindexing, delete and recreate
        client.delete_collection(name=collection_name)
    except Exception:
        pass

    # Create and populate
    collection = client.create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    chunks = _load_and_chunk_docs()
    if chunks:
        collection.add(
            ids=[c["chunk_id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[{"source": c["source"], "chunk_index": c["chunk_index"]} for c in chunks],
        )
        print(f"✅ ChromaDB indexed {len(chunks)} chunks from {len(set(c['source'] for c in chunks))} docs")

    _chroma_collection = collection
    return _chroma_collection


# ---------------------------------------------------------------------------
# BM25 indexing
# ---------------------------------------------------------------------------
def _get_bm25_index(force_reindex: bool = False):
    """Build or return the BM25 index over doc chunks."""
    global _bm25_index, _bm25_chunks

    if _bm25_index is not None and not force_reindex:
        return _bm25_index, _bm25_chunks

    chunks = _load_and_chunk_docs()
    tokenized = [_tokenize(c["text"]) for c in chunks]
    _bm25_index = BM25Okapi(tokenized)
    _bm25_chunks = chunks

    return _bm25_index, _bm25_chunks


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer for BM25."""
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return text.split()


# ---------------------------------------------------------------------------
# Hybrid retrieval with Reciprocal Rank Fusion
# ---------------------------------------------------------------------------
def _vector_search(query: str, top_k: int = 5) -> list[dict]:
    """Search ChromaDB for semantically similar chunks."""
    collection = _get_chroma_collection()
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    hits = []
    for i in range(len(results["ids"][0])):
        hits.append({
            "chunk_id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "source": results["metadatas"][0][i]["source"],
            "distance": results["distances"][0][i] if results.get("distances") else 0,
        })
    return hits


def _bm25_search(query: str, top_k: int = 5) -> list[dict]:
    """Search BM25 index for keyword-relevant chunks."""
    bm25, chunks = _get_bm25_index()
    tokens = _tokenize(query)
    scores = bm25.get_scores(tokens)

    # Get top_k indices
    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    hits = []
    for idx in ranked_indices:
        if scores[idx] > 0:
            hits.append({
                "chunk_id": chunks[idx]["chunk_id"],
                "text": chunks[idx]["text"],
                "source": chunks[idx]["source"],
                "score": float(scores[idx]),
            })
    return hits


def _reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
    top_n: int = 5,
) -> list[dict]:
    """
    Merge results from vector and BM25 search using Reciprocal Rank Fusion.
    RRF score = sum( 1 / (k + rank) ) for each result across lists.
    """
    scores: dict[str, float] = {}
    text_map: dict[str, dict] = {}

    # Score vector results
    for rank, hit in enumerate(vector_results):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        text_map[cid] = hit

    # Score BM25 results
    for rank, hit in enumerate(bm25_results):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        text_map[cid] = hit

    # Sort by fused score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

    results = []
    for cid, score in ranked:
        entry = text_map[cid].copy()
        entry["rrf_score"] = score
        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def index_documents(force: bool = False) -> int:
    """
    Index all documents into ChromaDB and BM25.
    Returns the number of chunks indexed.
    """
    collection = _get_chroma_collection(force_reindex=force)
    _get_bm25_index(force_reindex=force)
    return collection.count()


def rag_tool(user_query: str, top_k: int = 5) -> dict:
    """
    Hybrid RAG search: combines ChromaDB vector search with BM25 keyword search
    using Reciprocal Rank Fusion.

    Returns:
        dict with keys:
            - query: the original query
            - results: list of merged/ranked chunks
            - context: concatenated text for LLM consumption
            - error: error message if any, else None
    """
    try:
        vector_hits = _vector_search(user_query, top_k=top_k)
        bm25_hits = _bm25_search(user_query, top_k=top_k)
        merged = _reciprocal_rank_fusion(vector_hits, bm25_hits, top_n=top_k)

        context = "\n\n---\n\n".join(
            f"[Source: {r['source']}]\n{r['text']}" for r in merged
        )

        return {
            "query": user_query,
            "results": merged,
            "context": context,
            "error": None,
        }
    except Exception as e:
        return {
            "query": user_query,
            "results": [],
            "context": "",
            "error": str(e),
        }
