import os
from typing import List, Dict
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

# ============================================================
# Validation (fail fast)
# ============================================================
required = [
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_CHAT_DEPLOYMENT,
    AZURE_OPENAI_EMBED_DEPLOYMENT,
]

if not all(required):
    raise RuntimeError("❌ Missing required environment variables")

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
# Prompt
# ============================================================
SYSTEM_PROMPT = """
You are an internal enterprise knowledge assistant.

Rules:
- Use ONLY the provided Confluence content.
- Confluence is the single source of truth.
- Do NOT assume or hallucinate.
- If the answer is not found, respond with:
  "I could not find this information in Confluence."
- Be concise, factual, and clear.
"""

# ============================================================
# API Models
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
# Embedding
# ============================================================
def embed_query(query: str) -> List[float]:
    """
    Generate embedding for user query
    """
    resp = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=query,
    )
    return resp.data[0].embedding


# ============================================================
# Retrieval
# ============================================================
def retrieve_documents(query: str):
    """
    Vector search against Azure AI Search.
    Returns:
      - context chunks (for grounding)
      - top 6 related pages (title + url)
    """
    query_vector = embed_query(query)

    results = search_client.search(
        search_text=None,
        vector=query_vector,
        vector_fields="content_vector",
        top=20,
    )

    chunks: List[str] = []
    page_map: Dict[str, Dict] = {}

    for r in results:
        chunks.append(r["content"])

        page_id = r["page_id"]
        if page_id not in page_map:
            page_map[page_id] = {
                "title": r["title"],
                "url": r["url"],
                "score": r["@search.score"],
            }

    # Sort pages by relevance and keep top 6
    related_pages = sorted(
        page_map.values(),
        key=lambda x: x["score"],
        reverse=True,
    )[:6]

    return chunks[:6], related_pages


# ============================================================
# Prompt builder
# ============================================================
def build_messages(context_chunks: List[str], query: str) -> List[dict]:
    context_text = "\n\n".join(context_chunks)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
Context:
{context_text}

Question:
{query}
""",
        },
    ]


# ============================================================
# Answer generation
# ============================================================
def generate_answer(messages: List[dict]) -> str:
    completion = openai_client.chat.completions.create(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=messages,
        temperature=0,
    )

    return completion.choices[0].message.content.strip()


# ============================================================
# API Endpoint
# ============================================================
@app.post("/query", response_model=QueryResponse)
def query_rag(request: QueryRequest):
    try:
        context_chunks, related_pages = retrieve_documents(request.query)

        messages = build_messages(context_chunks, request.query)
        answer = generate_answer(messages)

        return QueryResponse(
            answer=answer,
            related_docs=[
                RelatedDoc(title=p["title"], url=p["url"])
                for p in related_pages
            ],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
