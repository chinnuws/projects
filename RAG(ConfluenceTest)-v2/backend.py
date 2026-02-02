"""
backend.py

FastAPI backend for Confluence RAG
- Azure AI Search (vector + semantic reranker)
- Azure OpenAI chat + embeddings
- Compatible with azure-search-documents 11.6.x
"""

import os
import logging
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Azure Search
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

# Azure OpenAI
from openai import AzureOpenAI

# --------------------------------------------------
# ENV
# --------------------------------------------------

load_dotenv()
logging.basicConfig(level=logging.INFO)

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")

TOP_K = int(os.getenv("TOP_K", "5"))

# --------------------------------------------------
# CLIENTS
# --------------------------------------------------

search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_INDEX,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

aoai = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version="2023-05-15",
)

# --------------------------------------------------
# FASTAPI
# --------------------------------------------------

app = FastAPI(title="Confluence RAG API")

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    sources: List[dict]

# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def embed_query(text: str) -> List[float]:
    resp = aoai.embeddings.create(
        model=EMBED_DEPLOYMENT,
        input=text,
    )
    return resp.data[0].embedding

def retrieve(query: str):
    query_vector = embed_query(query)

    results = search_client.search(
        search_text=query,  # lexical + semantic
        vector_queries=[{
            "kind": "vector",           # 🔥 REQUIRED (11.6.x+)
            "vector": query_vector,
            "fields": "vector",
            "k": TOP_K,
        }],
        query_type="semantic",
        semantic_configuration_name="default",
        top=TOP_K,
    )

    docs = []
    for r in results:
        docs.append({
            "title": r.get("title"),
            "content": r.get("content"),
            "url": r.get("url"),
            "score": r["@search.score"],
        })

    return docs

def generate_answer(query: str, docs: List[dict]) -> str:
    if not docs:
        return "I could not find relevant information in Confluence."

    context = "\n\n".join(
        f"Title: {d['title']}\nContent: {d['content']}"
        for d in docs
    )

    system_prompt = (
        "You are an internal knowledge assistant.\n"
        "Answer ONLY using the provided Confluence content.\n"
        "If the answer is not present, say you do not know.\n"
        "Be concise and accurate."
    )

    resp = aoai.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Question: {query}\n\nConfluence Content:\n{context}",
            },
        ],
    )

    return resp.choices[0].message.content.strip()

# --------------------------------------------------
# API
# --------------------------------------------------

@app.post("/query", response_model=QueryResponse)
def query_rag(req: QueryRequest):
    try:
        docs = retrieve(req.query)
        answer = generate_answer(req.query, docs)

        sources = [
            {
                "title": d["title"],
                "url": d["url"],
                "score": d["score"],
            }
            for d in docs
        ]

        return QueryResponse(answer=answer, sources=sources)

    except Exception as e:
        logging.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------------------------------
# HEALTH
# --------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}
