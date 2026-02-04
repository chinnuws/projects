import os
from typing import List, Dict, Tuple
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

# ============================================================
# Load environment variables
# ============================================================
load_dotenv()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")

# Validate required env vars early
required_envs = {
    "AZURE_SEARCH_ENDPOINT": AZURE_SEARCH_ENDPOINT,
    "AZURE_SEARCH_KEY": AZURE_SEARCH_KEY,
    "AZURE_SEARCH_INDEX": AZURE_SEARCH_INDEX,
    "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
    "AZURE_OPENAI_KEY": AZURE_OPENAI_KEY,
    "AZURE_OPENAI_CHAT_DEPLOYMENT": AZURE_OPENAI_CHAT_DEPLOYMENT,
    "AZURE_OPENAI_EMBED_DEPLOYMENT": AZURE_OPENAI_EMBED_DEPLOYMENT,
}

missing = [k for k, v in required_envs.items() if not v]
if missing:
    raise RuntimeError(f"❌ Missing environment variables: {missing}")

# ============================================================
# Clients
# ============================================================
search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY),
)

openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
)

# ============================================================
# FastAPI app
# ============================================================
app = FastAPI(title="Confluence RAG Backend")

# ============================================================
# Prompts
# ============================================================
SYSTEM_PROMPT = """
You are an internal enterprise knowledge assistant.

Rules:
- Use ONLY the provided Confluence context.
- Confluence is the single source of truth.
- Do NOT assume or hallucinate.
- If the answer is not found, respond with:
  "I could not find this information in Confluence."
- Be concise, accurate, and factual.
"""

# ============================================================
# API models
# ============================================================
class QueryRequest(BaseModel):
    query: str


class RelatedDoc(BaseModel):
    title: str
    url: str


class QueryResponse(BaseModel):
    answer: str
    related_docs: List[RelatedDoc]


# ============================================================
# Embedding helpers
# ============================================================
def embed_query(query: str) -> List[float]:
    """
    Convert a query into an embedding vector
    """
    try:
        resp = openai_client.embeddings.create(
            model=AZURE_OPENAI_EMBED_DEPLOYMENT,
            input=query,
        )
        return resp.data[0].embedding
    except Exception as e:
        raise RuntimeError(f"Embedding failed: {e}")


# ============================================================
# Retrieval helpers
# ============================================================
def retrieve_documents(query: str) -> Tuple[List[str], List[RelatedDoc]]:
    """
    Perform vector search and return:
      - top context chunks
      - top 6 unique Confluence pages (title + url)
    """
    query_vector = embed_query(query)

    try:
        results = search_client.search(
            search_text=None,
            vector=query_vector,
            vector_fields="content_vector",
            top=20,
        )
    except Exception as e:
        raise RuntimeError(f"Search failed: {e}")

    context_chunks: List[str] = []
    page_scores: Dict[str, Dict] = {}

    for r in results:
        # Context chunks for grounding
        if r.get("content"):
            context_chunks.append(r["content"])

        # Unique pages for references
        pid = r["page_id"]
        if pid not in page_scores:
            page_scores[pid] = {
                "title": r["title"],
                "url": r["url"],
                "score": r["@search.score"],
            }

    # Sort pages by relevance
    top_pages = sorted(
        page_scores.values(),
        key=lambda x: x["score"],
        reverse=True,
    )[:6]

    return (
        context_chunks[:6],
        [RelatedDoc(title=p["title"], url=p["url"]) for p in top_pages],
    )


# ============================================================
# Prompt construction
# ============================================================
def build_prompt(context_chunks: List[str], user_query: str) -> List[dict]:
    """
    Build messages payload for Chat Completion
    """
    context = "\n\n".join(context_chunks)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
Context:
{context}

Question:
{user_query}
""",
        },
    ]


# ============================================================
# Answer generation
# ============================================================
def generate_answer(messages: List[dict]) -> str:
    """
    Generate grounded answer using Azure OpenAI
    """
    try:
        completion = openai_client.chat.completions.create(
            model=AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=messages,
            temperature=0,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(f"Answer generation failed: {e}")


# ============================================================
# Main RAG flow
# ============================================================
def run_rag_pipeline(query: str) -> QueryResponse:
    """
    Full RAG pipeline:
    retrieve → prompt → generate
    """
    context_chunks, related_docs = retrieve_documents(query)
    messages = build_prompt(context_chunks, query)
    answer = generate_answer(messages)

    return QueryResponse(
        answer=answer,
        related_docs=related_docs,
    )


# ============================================================
# API endpoint
# ============================================================
@app.post("/query", response_model=QueryResponse)
def query_rag(request: QueryRequest):
    try:
        return run_rag_pipeline(request.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
