import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from openai import AzureOpenAI

# ---------------- ENV ----------------
load_dotenv()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")

# ---------------- CLIENTS ----------------
search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_INDEX,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2023-05-15",
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

app = FastAPI()

# ---------------- MODELS ----------------
class QueryRequest(BaseModel):
    query: str

# ---------------- PROMPT ----------------
SYSTEM_PROMPT = """You are a Confluence knowledge assistant.
Answer ONLY using the provided context.
If the answer is not found, say you don't know.
"""

# ---------------- HELPERS ----------------
def embed_query(text: str):
    return openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=text,
    ).data[0].embedding

def generate_answer(query: str, context: str):
    resp = openai_client.chat.completions.create(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{query}"},
        ],
    )
    return resp.choices[0].message.content

# ---------------- API ----------------
@app.post("/query")
def query_docs(req: QueryRequest):
    query_vector = embed_query(req.query)

    results = search_client.search(
        search_text=None,
        vector_queries=[
            {
                "vector": query_vector,
                "fields": "content_vector",
                "k": 6,
            }
        ],
        select=["title", "content", "url"],
    )

    docs = list(results)
    context = "\n\n".join(d["content"] for d in docs)

    answer = generate_answer(req.query, context)

    references = [
        {"title": d["title"], "url": d["url"]}
        for d in docs
    ]

    return {
        "answer": answer,
        "references": references
    }
