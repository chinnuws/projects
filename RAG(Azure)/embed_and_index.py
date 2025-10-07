# embed_and_index.py
import os
import uuid
import json
import tempfile
from typing import List
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
import requests

# -----------------------
# CONFIG - EDIT THESE
# -----------------------
SEARCH_ENDPOINT = "https://aisearchtestpoc.search.windows.net"
SEARCH_ADMIN_KEY = "vVg47I9vHDRz8l7y0wnnAiqo8O5k9RfeurUhetxG8gAzSeDtiViR"     # ADMIN key (Primary/Secondary)
SEARCH_QUERY_KEY = "fbtlxF9B29N2LxRI2Z0vsK6hwnKQuituvjOy0qT1BNAzSeDLvN7f"     # QUERY key (read-only)
OPENAI_API_KEY = "ClJj6Dn3XmMOSryoEKzlu872yUTypXQBuuxjPcYk6rAP7D8UM5cbJQQJ99BJACHYHv6XJ3w3AAAAACOGEsMJ"
OPENAI_ENDPOINT = "https://chinn-mggrqxtq-eastus2.services.ai.azure.com"  # no trailing slash
EMBED_ENGINE = "text-embedding-ada-002"
GPT_DEPLOYMENT = "gpt-35-turbo"
VECTOR_DIM = 1536

# API versions
SEARCH_API_VERSION = "2023-07-01-preview"   # must match index creation shape
OPENAI_API_VERSION = "2024-12-01-preview"

# -----------------------
# FASTAPI APP
# -----------------------
app = FastAPI(title="RAG Backend (REST search/fixed)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------
# Helper SearchClient factories
# -----------------------
def get_search_client_for_upload(index_name: str) -> SearchClient:
    return SearchClient(endpoint=SEARCH_ENDPOINT, index_name=index_name, credential=AzureKeyCredential(SEARCH_ADMIN_KEY))

def get_search_client_for_query(index_name: str) -> SearchClient:
    return SearchClient(endpoint=SEARCH_ENDPOINT, index_name=index_name, credential=AzureKeyCredential(SEARCH_QUERY_KEY))

# -----------------------
# REST index creation (2023-07-01-preview)
# -----------------------
def create_index_if_needed(index_name: str):
    get_url = f"{SEARCH_ENDPOINT}/indexes/{index_name}?api-version={SEARCH_API_VERSION}"
    headers = {"api-key": SEARCH_ADMIN_KEY, "Content-Type": "application/json"}
    resp = requests.get(get_url, headers=headers)
    if resp.status_code == 200:
        print(f"[index][REST] Index '{index_name}' already exists.")
        return
    if resp.status_code not in (404,):
        print(f"[index][REST] Unexpected status when checking index: {resp.status_code} {resp.text}")

    print(f"[index][REST] Creating index '{index_name}' (preview shape)...")
    algo_name = "my-vector-config"
    index_definition = {
        "name": index_name,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "content", "type": "Edm.String", "searchable": True, "analyzer": "en.lucene"},
            {
                "name": "embedding",
                "type": "Collection(Edm.Single)",
                "dimensions": VECTOR_DIM,
                "vectorSearchConfiguration": algo_name,
            },
        ],
        "vectorSearch": {
            "algorithmConfigurations": [
                {
                    "name": algo_name,
                    "kind": "hnsw",
                    "hnswParameters": {"metric": "cosine", "m": 16, "efConstruction": 200},
                }
            ]
        },
    }

    create_url = f"{SEARCH_ENDPOINT}/indexes?api-version={SEARCH_API_VERSION}"
    create_resp = requests.post(create_url, headers=headers, data=json.dumps(index_definition))
    if create_resp.status_code in (200, 201):
        print(f"[index][REST] Created index '{index_name}'.")
        return
    msg = f"[index][REST] Failed to create index: {create_resp.status_code}: {create_resp.text}"
    print(msg)
    raise Exception(msg)

# -----------------------
# Azure OpenAI REST helpers
# -----------------------
def azure_openai_embeddings(texts: List[str]) -> List[List[float]]:
    url = f"{OPENAI_ENDPOINT}/openai/deployments/{EMBED_ENGINE}/embeddings?api-version={OPENAI_API_VERSION}"
    headers = {"api-key": OPENAI_API_KEY, "Content-Type": "application/json"}
    payload = {"input": texts}
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        raise Exception(f"[openai][embeddings] HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    return [item["embedding"] for item in data["data"]]

def azure_openai_chat(prompt: str, max_tokens: int = 512, temperature: float = 0.2) -> str:
    url = f"{OPENAI_ENDPOINT}/openai/deployments/{GPT_DEPLOYMENT}/chat/completions?api-version={OPENAI_API_VERSION}"
    headers = {"api-key": OPENAI_API_KEY, "Content-Type": "application/json"}
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code == 404:
        # More explicit and actionable message for the user/frontend
        raise Exception(f"DeploymentNotFound: deployment '{GPT_DEPLOYMENT}' not found on resource. "
                        f"Check Azure Portal -> OpenAI -> Deployments, or run GET {OPENAI_ENDPOINT}/openai/deployments?api-version={OPENAI_API_VERSION}")
    if resp.status_code != 200:
        raise Exception(f"[openai][chat] HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        return str(data)

# -----------------------
# Chunking & Upload (admin key)
# -----------------------
def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def upload_chunks(index_name: str, chunks: List[str]):
    print(f"[upload] Uploading {len(chunks)} chunk(s) to index '{index_name}'")
    search_client = get_search_client_for_upload(index_name)

    embeddings = azure_openai_embeddings(chunks)
    print(f"[embed] Got {len(embeddings)} embeddings")

    for i, emb in enumerate(embeddings):
        if len(emb) != VECTOR_DIM:
            raise ValueError(f"Embedding length mismatch for chunk {i}: {len(emb)} vs {VECTOR_DIM}")

    docs = [{"id": str(uuid.uuid4()), "content": c, "embedding": e} for c, e in zip(chunks, embeddings)]
    result = search_client.upload_documents(docs)
    succeeded = all(getattr(r, "succeeded", False) for r in result)
    errors = []
    for r in result:
        if not getattr(r, "succeeded", False):
            errors.append({"key": getattr(r, "key", None), "error": getattr(r, "errorMessage", None)})
    print(f"[upload] Indexing results: succeeded={succeeded}, errors={errors}")
    return {"succeeded": succeeded, "errors": errors, "raw": str(result)}

# -----------------------
# REST vector search (fixed select type)
# -----------------------
def rest_vector_search(index_name: str, query_vec: List[float], k: int = 3):
    """
    Use the Search Documents REST endpoint with a 'vectors' parameter (preview).
    NOTE: 'select' must be a string (comma-delimited) for 2023-07-01-preview.
    """
    url = f"{SEARCH_ENDPOINT}/indexes/{index_name}/docs/search?api-version={SEARCH_API_VERSION}"
    headers = {"api-key": SEARCH_QUERY_KEY, "Content-Type": "application/json"}
    body = {
        # for vector-only search the value of "search" is ignored; using "*" is fine per docs
        "search": "*",
        "vectors": [
            {
                "value": query_vec,
                "fields": "embedding",
                "k": k
            }
        ],
        # <-- IMPORTANT: select is a comma-delimited string, not an array
        "select": "content"
    }
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code != 200:
        raise Exception(f"[search][rest] HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    # result docs typically under "value"
    return data.get("value", [])

# -----------------------
# Index statistics (new endpoint) - admin key
# -----------------------
@app.get("/api/index_status/{index_name}")
async def index_status(index_name: str):
    """
    Returns index statistics (document count) using the REST API (admin key).
    """
    try:
        url = f"{SEARCH_ENDPOINT}/indexes/{index_name}/stats?api-version={SEARCH_API_VERSION}"
        headers = {"api-key": SEARCH_ADMIN_KEY}
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return {"status": "error", "http_status": resp.status_code, "body": resp.text}
        data = resp.json()
        # sample output contains "documentCount"
        return {"status": "success", "stats": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -----------------------
# Prompt & RAG generator
# -----------------------
def generate_answer_with_context(question: str, contextdocs: List[str]) -> str:
    contexttext = "\n---\n".join(contextdocs)
    prompt = (
        "You are a helpful assistant that answers questions using the provided context."
        " If the answer cannot be found in the context, say 'I don't have enough information to answer that.'"
        " Use only information contained in the context below."
        " Context:\n" + contexttext +
        "\nQuestion: " + question +
        "\nAnswer (in one or two sentences, using only the relevant part of the context):"
    )
    return azure_openai_chat(prompt, max_tokens=256, temperature=0.2)

# -----------------------
# API endpoints (embed & chat)
# -----------------------
@app.post("/api/embed_index")
async def embed_index(file: UploadFile = File(...)):
    try:
        print(f"[api] Received: {file.filename}")
        with tempfile.NamedTemporaryFile(delete=False) as tmpf:
            tmpf.write(await file.read())
            tmpf.flush()
            fp = tmpf.name
        print(f"[api] Saved to {fp}")

        index_name = os.path.splitext(file.filename)[0].lower()
        create_index_if_needed(index_name)

        with open(fp, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = chunk_text(text)
        print(f"[api] Chunked into {len(chunks)} chunk(s)")

        upload_result = upload_chunks(index_name, chunks)
        os.remove(fp)
        return {"status": "success", "index_name": index_name, "uploaded_chunks": len(chunks), "upload_result": upload_result}
    except Exception as e:
        print(f"[api][error] {repr(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/api/chat")
async def chat_endpoint(payload: dict):
    try:
        question = payload.get("text", "")
        index_name = payload.get("index_name", "")
        k = int(payload.get("k", 3))
        if not question:
            return {"answer": "No question provided."}
        if not index_name:
            return {"answer": "Missing index_name parameter."}

        print(f"[chat] Question for index '{index_name}': {question}")
        query_vec = azure_openai_embeddings([question])[0]
        if len(query_vec) != VECTOR_DIM:
            return {"answer": f"Embedding size mismatch: {len(query_vec)} != {VECTOR_DIM}"}

        results = rest_vector_search(index_name, query_vec, k=k)
        retrieved = []
        for r in results:
            if "content" in r:
                retrieved.append(r["content"])
            elif "document" in r and isinstance(r["document"], dict) and "content" in r["document"]:
                retrieved.append(r["document"]["content"])
            else:
                retrieved.append(json.dumps(r))

        print(f"[chat] Retrieved {len(retrieved)} chunks")
        if not retrieved:
            return {"answer": "No relevant context found.", "context_used": []}

        answer = generate_answer_with_context(question, retrieved)
        return {"answer": answer, "context_used": retrieved}
    except Exception as e:
        print(f"[chat][error] {repr(e)}")
        return {"answer": f"Error: {str(e)}"}
