import os
import logging
from typing import List, Dict

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

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

TOP_K = 5

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
# API
# --------------------------------------------------

app = FastAPI()

class QueryRequest(BaseModel):
    query: str

class Citation(BaseModel):
    title: str
    url: str
    score: float

class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]

# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def embed_query(text: str) -> List[float]:
    resp = aoai.embeddings.create(
        model=EMBED_DEPLOYMENT,
        input=[text],
    )
    return resp.data[0].embedding

def retrieve(query: str) -> List[Dict]:
    vector = embed_query(query)

    results = search_client.search(
        search_text=query,
        vector_queries=[{
            "vector": vector,
            "k": TOP_K,
            "fields": "vector",
        }],
        query_type="semantic",
        semantic_configuration_name="default",
        top=TOP_K,
    )

    docs = []
    for r in results:
        docs.append({
            "content": r["content"],
            "title": r["title"],
            "url": r["url"],
            "score": r["@search.reranker_score"],
        })
    return docs

def generate_answer(query: str, docs: List[Dict]) -> str:
    context = "\n\n".join(
        [f"[{i+1}] {d['content']}" for i, d in enumerate(docs)]
    )

    system_prompt = (
        "You are a Confluence assistant. "
        "Answer ONLY using the provided context. "
        "If the answer is not present, say: "
        "'Not available in Confluence.'"
    )

    resp = aoai.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ],
    )

    return resp.choices[0].message.content

# --------------------------------------------------
# ENDPOINT
# --------------------------------------------------

@app.post("/query", response_model=QueryResponse)
def query_rag(req: QueryRequest):
    docs = retrieve(req.query)
    answer = generate_answer(req.query, docs)

    citations = [
        Citation(
            title=d["title"],
            url=d["url"],
            score=d["score"],
        )
        for d in docs
    ]

    return QueryResponse(answer=answer, citations=citations)
