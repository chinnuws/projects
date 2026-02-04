import os
from typing import List
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

# --------------------------------------------------
# Load env
# --------------------------------------------------
load_dotenv()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

# --------------------------------------------------
# Clients
# --------------------------------------------------
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

# --------------------------------------------------
# Prompts
# --------------------------------------------------
SYSTEM_PROMPT = """
You are an internal knowledge assistant.
Answer questions using ONLY the provided Confluence context.

Rules:
- Use Confluence content as the single source of truth.
- If the answer is not present in the context, say:
  "I could not find this information in Confluence."
- Do NOT assume, infer, or hallucinate.
- Be concise and factual.
"""

# --------------------------------------------------
# Models
# --------------------------------------------------
class QueryRequest(BaseModel):
    query: str


class RelatedDoc(BaseModel):
    title: str
    url: str


class QueryResponse(BaseModel):
    answer: str
    related_docs: List[RelatedDoc]


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def embed_query(text: str) -> List[float]:
    resp = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=text,
    )
    return resp.data[0].embedding


def retrieve(query: str):
    vector = embed_query(query)

    results = search_client.search(
        search_text=None,
        vector=vector,
        vector_fields="content_vector",
        top=20,
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
        reverse=True,
    )[:6]

    return chunks[:6], top_links


# --------------------------------------------------
# API
# --------------------------------------------------
@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    chunks, links = retrieve(req.query)

    context = "\n\n".join(chunks)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
Context:
{context}

Question:
{req.query}
"""
        },
    ]

    completion = openai_client.chat.completions.create(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=messages,
        temperature=0,
    )

    return QueryResponse(
        answer=completion.choices[0].message.content,
        related_docs=links,
    )
