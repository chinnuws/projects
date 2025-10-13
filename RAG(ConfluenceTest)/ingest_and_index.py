"""
ingest_and_index.py
Single-file incremental ingest for Confluence -> Azure Cognitive Search (vector index).
"""

import os
import json
import time
from typing import List, Dict, Any
from urllib.parse import urljoin
import logging
import requests
from html import unescape
import re
from dotenv import load_dotenv
load_dotenv()

# Azure Search
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile
)
from azure.search.documents import SearchClient

# Azure OpenAI
from openai import AzureOpenAI

# ----- Config (from env) -----
CONFLUENCE_BASE = os.getenv("CONFLUENCE_BASE")
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "confluence-vector-index")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
STATE_FILE = os.getenv("STATE_FILE", "./confluence_ingest_state.json")
CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "3000"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "400"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))

logging.basicConfig(level=logging.INFO)

# ----- Basic validation -----
for name, val in [
    ("CONFLUENCE_BASE", CONFLUENCE_BASE),
    ("CONFLUENCE_USER", CONFLUENCE_USER),
    ("CONFLUENCE_API_TOKEN", CONFLUENCE_API_TOKEN),
    ("SPACE_KEY", SPACE_KEY),
    ("AZURE_SEARCH_ENDPOINT", AZURE_SEARCH_ENDPOINT),
    ("AZURE_SEARCH_KEY", AZURE_SEARCH_KEY),
    ("AZURE_OPENAI_ENDPOINT", AZURE_OPENAI_ENDPOINT),
    ("AZURE_OPENAI_KEY", AZURE_OPENAI_KEY),
    ("EMBED_DEPLOYMENT", EMBED_DEPLOYMENT)
]:
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")

# Configure Azure OpenAI client
client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2023-05-15",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {"indexed_pages": {}, "last_run": None, "index_initialized": False}

def save_state(state: Dict[str, Any]):
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)

def chunk_text(text: str, max_chars=CHUNK_MAX_CHARS, overlap=CHUNK_OVERLAP_CHARS) -> List[str]:
    if overlap >= max_chars:
        raise ValueError("CHUNK_OVERLAP_CHARS must be less than CHUNK_MAX_CHARS")
    chunks = []
    n = len(text)
    i = 0
    while i < n:
        end = min(i + max_chars, n)
        chunks.append(text[i:end])
        i += max_chars - overlap
    return [c for c in chunks if c]

def embed_texts(texts: List[str]) -> List[List[float]]:
    try:
        resp = client.embeddings.create(model=EMBED_DEPLOYMENT, input=texts)
        return [d.embedding for d in resp.data]
    except Exception as e:
        logging.error(f"Embedding failed for batch of size {len(texts)}: {e}")
        return [[0.0] * 1536 for _ in texts]

# ----- Azure Search index management -----
def list_indexes() -> List[str]:
    idx_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=AzureKeyCredential(AZURE_SEARCH_KEY))
    return [n for n in idx_client.list_index_names()]

def ensure_index_exists():
    idx_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=AzureKeyCredential(AZURE_SEARCH_KEY))
    existing = [n for n in idx_client.list_index_names()]
    if AZURE_SEARCH_INDEX in existing:
        print("Index exists:", AZURE_SEARCH_INDEX)
        return

    # Determine vector dim from a sample embed
    sample_dim = len(embed_texts(["hello world"])[0])
    print("Creating index with vector dim:", sample_dim)

    # Configure vector search
    vector_search = VectorSearch(
        profiles=[VectorSearchProfile(name="my-vector-profile", algorithm_configuration_name="my-hnsw")],
        algorithms=[HnswAlgorithmConfiguration(name="my-hnsw")]
    )

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
        SimpleField(name="page_id", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="url", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="last_modified", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SimpleField(name="version", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SimpleField(name="space", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="labels", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
        SimpleField(name="has_video", type=SearchFieldDataType.Boolean, filterable=True),  # NEW FIELD
        # Use SearchField for vector
        SearchField(
            name="vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=sample_dim,
            vector_search_profile_name="my-vector-profile"
        )
    ]

    index = SearchIndex(name=AZURE_SEARCH_INDEX, fields=fields, vector_search=vector_search)
    idx_client.create_index(index)
    print("Index created:", AZURE_SEARCH_INDEX)

# ----- Index client helpers -----
def get_doc_client() -> SearchClient:
    return SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=AZURE_SEARCH_INDEX, credential=AzureKeyCredential(AZURE_SEARCH_KEY))

def upsert_documents(docs: List[Dict[str, Any]]):
    if not docs:
        return
    doc_client = get_doc_client()
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i+BATCH_SIZE]
        doc_client.upload_documents(documents=batch)
        print(f"Uploaded batch {i//BATCH_SIZE + 1} size {len(batch)}")

def delete_docs_by_page_id(page_id: str):
    doc_client = get_doc_client()
    results = doc_client.search(search_text="*", filter=f"page_id eq '{page_id}'", select=["id"], top=1000)
    ids = [r["id"] for r in results]
    if not ids:
        return
    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[i:i+BATCH_SIZE]
        actions = [{"@search.action": "delete", "id": id_} for id_ in batch_ids]
        doc_client.index_documents(actions)
        print(f"Deleted {len(batch_ids)} docs for page {page_id}")

def list_space_pages(space_key: str, start=0, limit=50):
    """Fetch pages from Confluence space"""
    url = f"{CONFLUENCE_BASE}/rest/api/content"
    params = {
        "spaceKey": space_key,
        "type": "page",
        "start": start,
        "limit": limit,
        "expand": "version"
    }
    resp = requests.get(url, params=params, auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN))
    resp.raise_for_status()
    return resp.json()

def fetch_page(page_id: str):
    """Fetch full page content"""
    url = f"{CONFLUENCE_BASE}/rest/api/content/{page_id}"
    params = {"expand": "body.storage,version,metadata.labels,_links.webui"}
    resp = requests.get(url, params=params, auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN))
    resp.raise_for_status()
    return resp.json()

def convert_storage_to_text(storage_html: str) -> str:
    """Convert Confluence storage format to plain text"""
    text = re.sub(r'<[^>]+>', ' ', storage_html)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def has_video_content(storage_html: str) -> bool:
    """Detect if page contains video content"""
    # Confluence video patterns
    video_patterns = [
        r'<ac:structured-macro[^>]*ac:name=["\']multimedia["\']',
        r'<ac:structured-macro[^>]*ac:name=["\']widget["\']',
        r'<iframe[^>]*>',
        r'<video[^>]*>',
        r'<embed[^>]*type=["\']video',
        r'\.mp4["\']',
        r'\.webm["\']',
        r'\.mov["\']',
        r'youtube\.com',
        r'vimeo\.com',
        r'youtu\.be'
    ]
    
    for pattern in video_patterns:
        if re.search(pattern, storage_html, re.IGNORECASE):
            return True
    return False

# ----- Main ingest logic -----
def run_ingest():
    state = load_state()
    ensure_index_exists()
    state["index_initialized"] = True

    # list pages
    pages = []
    start = 0
    limit = 50
    while True:
        resp = list_space_pages(SPACE_KEY, start=start, limit=limit)
        results = resp.get("results", [])
        if not results:
            break
        pages.extend(results)
        if len(results) < limit:
            break
        start += limit

    print("Pages found:", len(pages))
    current_versions = {p["id"]: p["version"]["number"] for p in pages}

    # detect deletions
    previously_indexed = state.get("indexed_pages", {})
    deleted = [pid for pid in previously_indexed.keys() if pid not in current_versions]
    if deleted:
        print("Deleted pages detected:", deleted)
        for pid in deleted:
            delete_docs_by_page_id(pid)
            state["indexed_pages"].pop(pid, None)

    # detect new or changed pages
    to_update = []
    for p in pages:
        pid = p["id"]
        ver = p["version"]["number"]
        if pid not in previously_indexed or previously_indexed.get(pid) != ver:
            to_update.append(pid)

    print("Pages to update (new/changed):", len(to_update))

    all_docs = []
    for pid in to_update:
        page = fetch_page(pid)
        title = page.get("title", "")
        # try better url from _links if available
        links = page.get("_links", {})
        webui = links.get("webui")
        if webui:
            url = urljoin(CONFLUENCE_BASE, webui)
        else:
            url = urljoin(CONFLUENCE_BASE, f"/spaces/{SPACE_KEY}/pages/{pid}")

        storage = page.get("body", {}).get("storage", {}).get("value", "")
        text = convert_storage_to_text(storage)
        has_video = has_video_content(storage)  # NEW: Detect video

        chunks = chunk_text(text)
        labels = []
        if page.get("metadata", {}).get("labels"):
            labels = [l.get("name") for l in page["metadata"]["labels"].get("results", [])]

        last_modified = page.get("version", {}).get("when")
        version_num = page.get("version", {}).get("number", 1)

        # embeddings in batches
        for i in range(0, len(chunks), BATCH_SIZE):
            batch_chunks = chunks[i:i+BATCH_SIZE]
            embeddings = embed_texts(batch_chunks)
            for j, ch in enumerate(batch_chunks):
                idx = i + j
                doc = {
                    "id": f"{pid}_{idx}",
                    "page_id": pid,
                    "title": title,
                    "content": ch,
                    "url": url,
                    "last_modified": last_modified,
                    "version": version_num,
                    "space": SPACE_KEY,
                    "labels": labels,
                    "has_video": has_video,  # NEW FIELD
                    "vector": embeddings[j]
                }
                all_docs.append(doc)

    if all_docs:
        upsert_documents(all_docs)

    # update state
    for pid in to_update:
        state["indexed_pages"][pid] = current_versions.get(pid)

    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_state(state)
    print("Ingest complete. Indexed docs:", len(all_docs))

if __name__ == "__main__":
    run_ingest()
