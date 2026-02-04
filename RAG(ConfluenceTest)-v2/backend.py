import os
import logging
from typing import List, Dict
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

# ============================================================
# Load env
# ============================================================
load_dotenv()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")

TOP_K = int(os.getenv("TOP_K", "10"))
TOP_LINKS = 6

# ============================================================
# Clients
# ============================================================
search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_INDEX,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

aoai = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
)

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ============================================================
# Models
# ============================================================
class QueryRequest(BaseModel):
    query: str

class Source(BaseModel):
    title: str
    url: str

class QueryResponse(BaseModel):
    answer: str
    sources: List[Source]

# ============================================================
# Helpers
# ============================================================
def embed_query(text: str) -> List[float]:
    resp = aoai.embeddings.create(
        model=EMBED_DEPLOYMENT,
        input=text,
    )
    return resp.data[0].embedding


def retrieve(query: str) -> List[Dict]:
    vector = embed_query(query)

    results = search_client.search(
        search_text=query,
        vector_queries=[{
            "kind": "vector",
            "vector": vector,
            "fields": "content_vector",
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


def generate_answer(query: str, docs: List[Dict]) -> str:
    if not docs:
        return "I could not find this information in Confluence."

    context = "\n\n".join(
        f"{d['title']}:\n{d['content']}"
        for d in docs
    )

    system_prompt = (
        "You are an internal knowledge assistant.\n"
        "Use ONLY the provided Confluence content.\n"
        "If the answer is not present, say you do not know."
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

# ============================================================
# API
# ============================================================
@app.post("/query", response_model=QueryResponse)
def query_rag(req: QueryRequest):
    try:
        docs = retrieve(req.query)
        answer = generate_answer(req.query, docs)

        # ✅ De-duplicate & rank links
        page_map = {}
        for d in docs:
            key = (d["title"], d["url"])
            if key not in page_map or d["score"] > page_map[key]["score"]:
                page_map[key] = d

        sources = sorted(
            page_map.values(),
            key=lambda x: x["score"],
            reverse=True,
        )[:TOP_LINKS]

        return QueryResponse(
            answer=answer,
            sources=[
                Source(title=s["title"], url=s["url"])
                for s in sources
            ],
        )

    except Exception as e:
        logging.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(e))
