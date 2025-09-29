from fastapi import FastAPI
from pydantic import BaseModel
import os, requests, json
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

app = FastAPI()

COG_ENDPOINT = os.getenv("COG_SEARCH_ENDPOINT")
COG_INDEX = os.getenv("COG_SEARCH_INDEX","confluence-index")
COG_KEY = os.getenv("COG_SEARCH_ADMIN_KEY")
OPENAI_ENDPT = os.getenv("AZ_OPENAI_ENDPOINT")
OPENAI_KEY = os.getenv("AZ_OPENAI_API_KEY")
OPENAI_DEPLOYMENT = os.getenv("AZ_OPENAI_DEPLOYMENT")

search_client = SearchClient(endpoint=COG_ENDPOINT, index_name=COG_INDEX, credential=AzureKeyCredential(COG_KEY))

class QueryRequest(BaseModel):
    q: str
    top_k: int = 5
    rerank_with_rag: bool = True

def embed_query(text: str):
    url = OPENAI_ENDPT.rstrip("/") + f"/openai/deployments/{OPENAI_DEPLOYMENT}/embeddings?api-version=2024-06-01-preview"
    headers = {"api-key": OPENAI_KEY, "Content-Type": "application/json"}
    resp = requests.post(url, json={"input": text}, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]

@app.post("/query")
def query(req: QueryRequest):
    qvec = embed_query(req.q)
    # Azure Search vector query payload
    vector_query = {
        "vector": {
            "field": "embedding",
            "k": req.top_k,
            "value": qvec
        },
        "select": ["id", "title", "content", "sourceUrl", "chunkIndex"],
        "top": req.top_k
    }
    # use the Azure Search REST API for vector queries (or SDK supports it)
    search_url = COG_ENDPOINT.rstrip("/") + f"/indexes/{COG_INDEX}/docs/search?api-version=2024-07-01"
    headers = {"api-key": COG_KEY, "Content-Type": "application/json"}
    payload = {
        "vector": {
            "k": req.top_k,
            "fields": ["embedding"],
            "value": qvec
        },
        "select": ["id","title","content","sourceUrl","chunkIndex"]
    }
    r = requests.post(search_url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    resp = r.json()
    results = []
    for doc in resp.get("value", []):
        results.append({
            "id": doc.get("id"),
            "title": doc.get("title"),
            "content": doc.get("content"),
            "url": doc.get("sourceUrl")
        })
    # optional RAG step
    if req.rerank_with_rag:
        # build prompt using top docs
        snippets = "\n\n---\n\n".join([f"TITLE: {d['title']}\nURL: {d['url']}\n\n{d['content']}" for d in results])
        prompt = f"Use the following documents to answer the question. If the answer is not in the docs, say 'I don't know'.\n\nDocuments:\n{snippets}\n\nQuestion: {req.q}\n\nAnswer:"
        # call OpenAI completions (Azure OpenAI)
        comp_url = OPENAI_ENDPT.rstrip("/") + f"/openai/deployments/{OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-06-01-preview"
        headers = {"api-key": OPENAI_KEY, "Content-Type": "application/json"}
        body = {
            "messages": [{"role":"system","content":"You are a helpful assistant that answers only using the provided documents."},
                         {"role":"user","content": prompt}],
            "max_tokens": 300
        }
        rc = requests.post(comp_url, headers=headers, json=body, timeout=30)
        if rc.status_code == 200:
            j = rc.json()
            # depends on model/response format; adjust if different
            answer = j.get("choices",[{}])[0].get("message",{}).get("content","")
        else:
            answer = ""
    else:
        answer = ""
    return {"answer": answer, "sources": results}
