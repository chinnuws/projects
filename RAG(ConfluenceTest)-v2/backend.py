import os
from typing import List, Tuple
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

# Basic validation (fail fast)
required_envs = [
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_CHAT_DEPLOYMENT,
    AZURE_OPENAI_EMBED_DEPLOYMENT,
]
if not all(required_envs):
    raise RuntimeError("❌ Missing one or more required environment variables")

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

You MUST follow these rules:
- Answer using ONLY the provided Confluence context.
- Confluence is the single source of truth.
- If the answer is not found in the context, respond with:
  "I could not find this information in Confluence."
- Do NOT assume, infer, or hallucinate.
- Be concise, clear, and factual.
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
# Embedding
# ============================================================
def embed_query(query: str) -> List[float]:
    """
    Convert user query into embedding vector
    """
    response = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=query,
    )
    return response.data[0].embedding


# ============================================================
# Retrieval
# ============================================================
def retrieve_documents(query: str) -> Tuple[List[str], List[RelatedDoc]]:
    """
    Vector search against Azure AI Search.
    Returns:
      - top content chunks (for grounding)
      - top 6 unique related documents (title + url)
    """
    query_vector = embed_query(query)

    results = search_client.search(
        search_text=None,
        vector=query_vector,
        vector_fields="content_vector",
        top=20,
    )

    chunks: List[str] = []
    page_map = {}

    for result in results:
        # Collect chunk content for grounding
        chunks.append(result["content"])

        page_id = result["page_id"]
        if page_id not in page_map:
            page_map[page_id] = {
                "title": result["title"],
                "url": result["url"],
                "score": result["@search.score"],
            }

    # Rank pages by relevance score and keep top 6
    related_docs = sorted(
        page_map.values(),
        key=lambda x: x["score"],
        reverse=True,
    )[:6]

    return chunks[:6], [
        RelatedDoc(title=d["title"], url=d["url"]) for d in related_docs
    ]


# ============================================================
# Prompt construction
# ============================================================
def build_prompt(context_chunks: List[str], user_query: str) -> List[dict]:
    """
    Build messages payload for Chat Completion
    """
    context_text = "\n\n".join(context_chunks)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
Context:
{context_text}

Question:
{user_query}
"""
        },
    ]


# ============================================================
# Answer generation
# ============================================================
def generate_answer(messages: List[dict]) -> str:
    """
    Generate grounded answer from Azure OpenAI
    """
    completion = openai_client.chat.completions.create(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=messages,
        temperature=0,
    )

    return completion.choices[0].message.content.strip()


# ============================================================
# API endpoint
# ============================================================
@app.post("/query", response_model=QueryResponse)
def query_rag(request: QueryRequest):
    try:
        context_chunks, related_docs = retrieve_documents(request.query)

        messages = build_prompt(context_chunks, request.query)
        answer = generate_answer(messages)

        return QueryResponse(
            answer=answer,
            related_docs=related_docs,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
