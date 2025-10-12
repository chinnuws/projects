"""
FastAPI RAG endpoint (backend.py)
- /api/query : POST {query, top_k?}
  returns {"answer": "...", "sources":[{title,url,content,score}]}
  
This uses:
- Azure OpenAI embeddings for query
- Azure Cognitive Search vector search
- Azure OpenAI Chat for final answer
"""
import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv

load_dotenv()

from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential

# env config
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "confluence-vector-index")
EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")

# validate
for name, val in [
    ("AZURE_SEARCH_ENDPOINT", AZURE_SEARCH_ENDPOINT),
    ("AZURE_SEARCH_KEY", AZURE_SEARCH_KEY),
    ("AZURE_OPENAI_ENDPOINT", AZURE_OPENAI_ENDPOINT),
    ("AZURE_OPENAI_KEY", AZURE_OPENAI_KEY),
    ("EMBED_DEPLOYMENT", EMBED_DEPLOYMENT),
    ("CHAT_DEPLOYMENT", CHAT_DEPLOYMENT)
]:
    if not val:
        raise RuntimeError(f"Missing env var {name}")

# Azure OpenAI client
client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2023-05-15",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY)
)

app = FastAPI(title="Confluence RAG API")

class QueryReq(BaseModel):
    query: str
    top_k: int = 5

@app.post("/api/query")
def query_endpoint(req: QueryReq):
    q = req.query
    k = req.top_k if req.top_k and req.top_k > 0 else 5
    
    # 1) embed query
    q_emb = client.embeddings.create(model=EMBED_DEPLOYMENT, input=q).data[0].embedding
    
    # 2) vector search in Azure Cognitive Search
    vector_query = VectorizedQuery(vector=q_emb, k_nearest_neighbors=k, fields="vector")
    
    results = search_client.search(
        search_text="",
        vector_queries=[vector_query],
        select=["id", "title", "content", "url", "page_id", "last_modified"],
        filter=f"space eq '{SPACE_KEY}'" if SPACE_KEY else None
    )
    
    hits = []
    for r in results:
        hits.append({
            "id": r["id"],
            "title": r.get("title"),
            "content": r.get("content"),
            "url": r.get("url")
        })
    
    # 3) build prompt - NO INLINE CITATIONS
    snippets = []
    for i, h in enumerate(hits):
        snippet = h["content"]
        if len(snippet) > 900:
            snippet = snippet[:900] + "..."
        snippets.append(f"Source {i+1}: {h.get('title')}\n{snippet}\nURL: {h.get('url')}")
    
    system_prompt = "You are an assistant that answers questions based only on the provided Confluence sources. If the answer is not contained in the sources, say you don't know and suggest how to proceed."
    user_prompt = f"User question: {q}\n\nHere are the sources:\n\n" + "\n\n".join(snippets) + "\n\nAnswer concisely in a natural, conversational way without including source citations in your response."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    chat_resp = client.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        messages=messages,
        max_tokens=512,
        temperature=0.0
    )
    
    assistant_text = chat_resp.choices[0].message.content
    return {"answer": assistant_text, "sources": hits}
