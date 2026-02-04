import os
import traceback
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from openai import AzureOpenAI

# --------------------------------------------------
# ENV
# --------------------------------------------------
AZURE_SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
AZURE_SEARCH_KEY = os.environ["AZURE_SEARCH_KEY"]
AZURE_SEARCH_INDEX = os.environ["AZURE_SEARCH_INDEX"]

AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_KEY"]
AZURE_OPENAI_CHAT_DEPLOYMENT = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]
AZURE_OPENAI_EMBED_DEPLOYMENT = os.environ["AZURE_OPENAI_EMBED_DEPLOYMENT"]
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15")

TOP_K = 6

# --------------------------------------------------
# CLIENTS
# --------------------------------------------------
search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY)
)

openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

# --------------------------------------------------
# FASTAPI
# --------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # adjust for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# MODELS
# --------------------------------------------------
class QueryRequest(BaseModel):
    question: str

class RecommendedDoc(BaseModel):
    title: str
    url: str

class QueryResponse(BaseModel):
    answer: str
    recommended_docs: List[RecommendedDoc]

# --------------------------------------------------
# SYSTEM PROMPT
# --------------------------------------------------
SYSTEM_PROMPT = """
You are an internal documentation assistant.
Answer the user's question using ONLY the provided documentation context.
If the answer is not present, say you do not know.
Keep the answer concise and factual.
"""

# --------------------------------------------------
# EMBEDDINGS
# --------------------------------------------------
def embed_query(text: str) -> List[float]:
    resp = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=text
    )
    return resp.data[0].embedding

# --------------------------------------------------
# SEARCH
# --------------------------------------------------
def search_docs(query: str, vector: List[float]):
    results = search_client.search(
        search_text=query,
        vector=vector,
        top=TOP_K,
        vector_fields="content_vector",
        select=["content", "title", "url"]
    )
    return list(results)

# --------------------------------------------------
# ANSWER GENERATION
# --------------------------------------------------
def generate_answer(question: str, docs: list) -> str:
    context_blocks = []
    for d in docs:
        content = d.get("content", "")
        title = d.get("title", "")
        context_blocks.append(f"Title: {title}\n{content}")

    context = "\n\n---\n\n".join(context_blocks)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
Context:
{context}

Question:
{question}
"""
        }
    ]

    response = openai_client.chat.completions.create(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=messages,
        temperature=0.2,
        max_tokens=600
    )

    return response.choices[0].message.content.strip()

# --------------------------------------------------
# API
# --------------------------------------------------
@app.post("/query", response_model=QueryResponse)
def query_docs(req: QueryRequest):
    try:
        query_embedding = embed_query(req.question)
        search_results = search_docs(req.question, query_embedding)

        if not search_results:
            return QueryResponse(
                answer="I could not find relevant information in the documentation.",
                recommended_docs=[]
            )

        answer = generate_answer(req.question, search_results)

        # Top 6 unique recommended links (title + url only)
        seen = set()
        recommended = []
        for r in search_results:
            key = (r["title"], r["url"])
            if key not in seen:
                seen.add(key)
                recommended.append(
                    RecommendedDoc(
                        title=r["title"],
                        url=r["url"]
                    )
                )
            if len(recommended) == 6:
                break

        return QueryResponse(
            answer=answer,
            recommended_docs=recommended
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}
