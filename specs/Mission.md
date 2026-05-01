# Mission: HealthGuard Agentic RAG

## Vision
To provide US Health Insurance members with an intelligent, transparent, and multi-modal assistant that synthesizes information across structured databases, CSV provider lists, and unstructured policy PDFs.

## Problem Statement
Insurance members often need to combine data: "Which 'Silver' plan doctor is closest to me in Austin, Texas and what is my co-pay for a specialist visit?" This requires querying a SQL DB (Plans/Co-pays), a CSV (Providers/Locations), and Text Docs (Definitions).

## Primary Objectives
1.  **Spec-Driven Intelligence**: Use Llama 3 (Groq) with explicit schema awareness for zero-error code generation.
2.  **Hybrid Retrieval**: Combine BM25 keyword matching with ChromaDB vector embeddings for technical policy text.
3.  **Auditability**: Every decision must be traceable. We generate a `.jsonl` for machine auditing and a `.md` for human review per session.
4.  **Operational Efficiency**: Use `uv` for lightning-fast dependency management and `FastAPI` for a high-performance backend.

## Data Simulation Profile
- **SQL (Member Benefits)**: Detailed plan tiers, deductibles, and service-specific co-pays.
- **CSV (Provider Directory)**: 500+ records of doctors, NPI numbers, locations (City, State, Zip), and "Accepting New Patients" status.
- **Text (Policy Handbooks)**: "Exclusions.txt", "Member_Rights.txt", and "Claims_Process.txt".