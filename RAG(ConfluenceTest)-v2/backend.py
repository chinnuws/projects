import os
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

load_dotenv()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_INDEX,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
)

app = FastAPI()


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    answer: str
    related_docs: List[dict]


def embed_query(text: str):
    resp = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=text
    )
    return resp.data[0].embedding


def retrieve(query: str):
    vector = embed_query(query)

    results = search_client.search(
        search_text=None,
        vector=vector,
        top=20,
        vector_fields="content_vector",
    )

    pages = {}
    chunks = []

    for r in results:
        chunks.append(r["content"])
        pid = r["page_id"]

        if pid not in pages:
            pages[pid] = {
                "title": r["title"],
                "url": r["url"],
                "score": r["@search.score"],
            }

    top_links = sorted(
        pages.values(),
        key=lambda x: x["score"],
        reverse=True
    )[:6]

    return chunks, top_links


@app.post("/query", response_model=QueryResponse)
def query_rag(req: QueryRequest):
    chunks, links = retrieve(req.query)

    context = "\n".join(chunks[:6])

    prompt = f"""
Answer the question using the context below.

Context:
{context}

Question:
{req.query}
"""

    resp = openai_client.chat.completions.create(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return QueryResponse(
        answer=resp.choices[0].message.content,
        related_docs=links,
    )
