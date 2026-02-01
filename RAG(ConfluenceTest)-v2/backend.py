"""
backend.py
Production-grade FastAPI backend for Confluence RAG
Uses Azure AI Search Hybrid + Semantic Reranker
"""

import os
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential

# -------------------------------------------------
# ENV
# -------------------------------------------------

load_dotenv()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2023-05-15")

EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")

SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")

for name, val in [
    ("AZURE_SEARCH_ENDPOINT", AZURE_SEARCH_ENDPOINT),
    ("AZURE_SEARCH_KEY", AZURE_SEARCH_KEY),
    ("AZURE_SEARCH_INDEX", AZURE_SEARCH_INDEX),
    ("AZURE_OPENAI_ENDPOINT", AZURE_OPENAI_ENDPOINT),
    ("AZURE_OPENAI_KEY", AZURE_OPENAI_KEY),
    ("EMBED_DEPLOYMENT", EMBED_DEPLOYMENT),
    ("CHAT_DEPLOYMENT", CHAT_DEPLOYMENT),
]:
    if not val:
        raise RuntimeError(f"Missing env var: {name}")

# -------------------------------------------------
# CLIENTS
# -------------------------------------------------

aoai = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY),
)

# -------------------------------------------------
# API
# -------------------------------------------------

app = FastAPI(title="Confluence RAG API")

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def rewrite_query(user_query: str) -> str:
    """
    Rewrite user question into a clean documentation-style search query.
    """
    prompt = f"""
Rewrite the following user question into a concise search query
for internal Confluence documentation. Preserve technical intent.

User question:
{user_query}
"""

    resp = aoai.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=64,
    )

    return resp.choices[0].message.content.strip()


def embed_query(text: str) -> List[float]:
    return aoai.embeddings.create(
        model=EMBED_DEPLOYMENT,
        input=text,
    ).data[0].embedding


# -------------------------------------------------
# ENDPOINT
# -------------------------------------------------

@app.post("/api/query")
def query_confluence(req: QueryRequest):
    user_query = req.query
    top_k = min(max(req.top_k, 1), 8)

    # 1️⃣ Rewrite query (high impact)
    search_query = rewrite_query(user_query)

    # 2️⃣ Embed rewritten query
    query_vector = embed_query(search_query)

    # 3️⃣ Hybrid + Semantic Search (THIS ENABLES RERANKER)
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k * 4,
        fields="vector",
    )

    results = search_client.search(
        search_text=search_query,
        vector_queries=[vector_query],
        query_type="semantic",
        semantic_configuration_name="default",
        query_language="en-us",
        top=top_k * 4,
        select=["id", "page_id", "title", "content", "url"],
        filter=f"space eq '{SPACE_KEY}'" if SPACE_KEY else None,
    )

    # 4️⃣ Deduplicate AFTER semantic ranking (best chunk per page)
    hits = []
    seen_pages = set()

    for r in results:
        pid = r["page_id"]
        if pid in seen_pages:
            continue

        seen_pages.add(pid)
        hits.append({
            "title": r["title"],
            "content": r["content"],
            "url": r["url"],
            "page_id": pid,
        })

        if len(hits) >= top_k:
            break

    # 5️⃣ Build grounded prompt
    sources_text = []
    for i, h in enumerate(hits):
        snippet = h["content"][:900]
        sources_text.append(
            f"SOURCE {i+1}:\n"
            f"Title: {h['title']}\n"
            f"Content: {snippet}\n"
            f"URL: {h['url']}"
        )

    system_prompt = (
        "You are an enterprise knowledge assistant.\n"
        "Answer ONLY using the provided Confluence sources.\n"
        "If the answer is not present, say so clearly.\n"
        "Do NOT assume or invent information."
    )

    user_prompt = (
        f"User question:\n{user_query}\n\n"
        f"Confluence sources:\n\n"
        + "\n\n".join(sources_text)
    )

    # 6️⃣ Generate final answer
    response = aoai.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=900,
    )

    return {
        "answer": response.choices[0].message.content,
        "sources": hits,
        "search_query_used": search_query,
    }


@app.get("/health")
def health():
    return {"status": "ok"}
