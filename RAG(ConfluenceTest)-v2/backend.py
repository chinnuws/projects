import os
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# --------------------------------------------------
# ENV
# --------------------------------------------------
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_INDEX,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

# --------------------------------------------------
# MODELS
# --------------------------------------------------
class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    links: List[str]

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def embed_query(query: str) -> List[float]:
    resp = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        input=query
    )
    return resp.data[0].embedding

def retrieve(query: str):
    vector = embed_query(query)

    results = search_client.search(
        search_text=None,
        vector_queries=[{
            "kind": "vector",
            "vector": vector,
            "fields": "content_vector",
            "k": 6
        }],
        select=["title", "content", "url"],
    )

    docs = []
    for r in results:
        docs.append(r)

    return docs

def generate_answer(query: str, docs):
    context = "\n\n".join(d["content"] for d in docs)

    system_prompt = (
        "You are a helpful assistant. "
        "Answer ONLY using the provided Confluence documentation."
    )

    resp = openai_client.chat.completions.create(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
        ],
        temperature=0,
    )

    return resp.choices[0].message.content

# --------------------------------------------------
# API
# --------------------------------------------------
@app.post("/query", response_model=QueryResponse)
def query_rag(req: QueryRequest):
    docs = retrieve(req.query)
    answer = generate_answer(req.query, docs)

    links = []
    seen = set()
    for d in docs:
        if d["url"] not in seen:
            links.append(d["url"])
            seen.add(d["url"])

    return QueryResponse(
        answer=answer,
        links=links
    )
