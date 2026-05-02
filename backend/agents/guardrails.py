from typing import Tuple
from backend.core.llm import llm_completion

# Fallback Responses
FALLBACK_OUT_OF_SCOPE = "This system is designed to answer questions only from its authorized knowledge sources."
FALLBACK_NO_DATA = "No relevant information was found in the available knowledge sources."
FALLBACK_INSUFFICIENT_CONTEXT = "The available data is insufficient to provide a complete answer."

# Authorized Knowledge Boundaries (AKB) description
AKB_DESCRIPTION = "The system has access to a SQLite database, CSV files, and specific text documents."

def query_validator(user_query: str, conversation_history: str = "") -> Tuple[bool, str]:
    """
    Input Guardrail (Pre-Processing).
    Classifies whether the user query is within the Authorized Knowledge Boundary (AKB).
    Rejects general knowledge, hypothetical, or unrelated queries.
    Accepts conversation_history so follow-up queries with pronouns are understood in context.
    Returns: (is_valid: bool, fallback_message: str)
    """
    history_block = ""
    if conversation_history:
        history_block = f"""
    Recent Conversation History (for context — the user may be asking a follow-up):
    ---
    {conversation_history}
    ---
    """

    prompt = f"""
    You are an input guardrail for an enterprise system. 
    The system is STRICTLY restricted to answering queries using its Authorized Knowledge Base (AKB), which contains:
    - Relational data in a SQLite database
    - Tabular data in CSV files
    - Specific text documents
    {history_block}
    Your task is to determine if the user query is asking for general knowledge, opinions, hypothetical scenarios, or topics entirely outside the scope of querying internal enterprise documents and databases.
    - If the query looks like a legitimate search, follow-up question, data request, or clarification, return PASS.
    - If the query is conversational but clearly related to the ongoing search for enterprise information, return PASS.
    - ONLY return FAIL if the query is undeniably out of scope (e.g., "Write a poem", "What is the capital of France?").

    User Query: "{user_query}"

    Reply with ONLY the word PASS or FAIL on the first line.
    """
    try:
        verdict = llm_completion([{"role": "user", "content": prompt}], temperature=0, max_tokens=10).strip().upper()
        if verdict.startswith("FAIL"):
            return False, FALLBACK_OUT_OF_SCOPE
        return True, ""
    except Exception:
        # Fail open on LLM error to not break the system entirely.
        return True, ""

def context_validator(query: str, retrieved_context: str) -> Tuple[bool, str]:
    """
    Context Validation Layer.
    Checks if retrieved context is sufficient to answer the query.
    Returns: (is_sufficient: bool, fallback_message: str)
    """
    if not retrieved_context or retrieved_context.strip() == "":
        return False, FALLBACK_NO_DATA

    prompt = f"""
    You are a context validator for an enterprise system.
    Evaluate whether the provided context contains sufficient information to answer the user query.
    
    User Query: "{query}"
    
    Retrieved Context:
    ---
    {retrieved_context}
    ---
    
    - The Retrieved Context may contain raw data tables, executed code (SQL/Python), and Conversation History.
    - If the context contains the raw data OR the executed code that logically proves the answer to the query, it is sufficient.
    - Do not be overly rigid; if the data, code, or history combined provide enough information to logically form an answer, reply with PASS.
    - If the context is entirely empty, irrelevant, or vastly insufficient, reply with FAIL.
    
    Reply with ONLY the word PASS or FAIL on the first line.
    """
    try:
        verdict = llm_completion([{"role": "user", "content": prompt}], temperature=0, max_tokens=10).strip().upper()
        if verdict.startswith("FAIL"):
            return False, FALLBACK_INSUFFICIENT_CONTEXT
        return True, ""
    except Exception:
        return True, ""

def response_validator(query: str, context: str, response: str) -> bool:
    """
    Output Guardrails (Post-Processing).
    Verifies the response is grounded in the retrieved context and introduces no external knowledge.
    Returns: bool (True if valid, False if hallucinated/unsupported)
    """
    prompt = f"""
    You are an output guardrail for a strict enterprise AI system.
    Your task is to ensure the Assistant's Response is STRICTLY grounded in the Retrieved Context.
    
    User Query: "{query}"
    
    Retrieved Context:
    ---
    {context}
    ---
    
    Assistant Response:
    ---
    {response}
    ---
    
    Evaluate the Assistant Response against the Retrieved Context.
    - The Retrieved Context may contain Tool Results, Executed Code, and Conversation History.
    - Information found in the Conversation History OR the User Query is considered VALID and GROUNDED.
    - It is perfectly acceptable for the Assistant to repeat facts (like locations or names) previously mentioned by the user or in the history.
    - Do not penalize the Assistant for summarizing data or stating the logical result of the Executed Code.
    - If the response contains ANY external facts, numbers, names, or assertions that are NOT explicitly present in the Tool Results, Executed Code, Conversation History, NOR the User Query, you must reject it.
    - It is completely ACCEPTABLE for the response to state that certain information is missing or not provided. Do NOT reject the response for admitting a lack of information.
    
    If the response is fully grounded (or correctly states info is missing), reply with ONLY the word: PASS
    If the response contains ungrounded information, external knowledge, or hallucinations, reply with ONLY the word: FAIL
    """
    try:
        verdict = llm_completion([{"role": "user", "content": prompt}], temperature=0, max_tokens=10).strip().upper()
        if verdict.startswith("FAIL"):
            return False
        return True
    except Exception:
        return True
