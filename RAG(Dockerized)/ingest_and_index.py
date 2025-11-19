"""
ingest_and_index.py
Kubernetes-ready with Azure Blob Storage for state persistence
All config from environment variables (ConfigMap/Secrets)
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

# Azure SDK imports
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SimpleField, SearchableField, SearchField,
    SearchFieldDataType, VectorSearch, HnswAlgorithmConfiguration,
    VectorSearchProfile
)
from azure.search.documents import SearchClient
from openai import AzureOpenAI
from azure.storage.blob import BlobServiceClient

# ----- Get all config from environment variables (set by K8s) -----
CONFLUENCE_BASE = os.environ.get("CONFLUENCE_BASE")
CONFLUENCE_USER = os.environ.get("CONFLUENCE_USER")
CONFLUENCE_API_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN")
SPACE_KEY = os.environ.get("CONFLUENCE_SPACE_KEY")
AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.environ.get("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.environ.get("AZURE_SEARCH_INDEX", "confluence-vector-index")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.environ.get("AZURE_OPENAI_KEY")
EMBED_DEPLOYMENT = os.environ.get("AZURE_OPENAI_EMBED_DEPLOYMENT")
CHAT_DEPLOYMENT = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT")

# Azure Blob Storage config
AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
BLOB_CONTAINER_NAME = os.environ.get("BLOB_CONTAINER_NAME", "confluence-state")
STATE_BLOB_NAME = "confluence_ingest_state.json"

# Processing parameters
CHUNK_MAX_CHARS = int(os.environ.get("CHUNK_MAX_CHARS", "3000"))
CHUNK_OVERLAP_CHARS = int(os.environ.get("CHUNK_OVERLAP_CHARS", "400"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "32"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate required environment variables
required_env_vars = [
    "CONFLUENCE_BASE",
    "CONFLUENCE_USER",
    "CONFLUENCE_API_TOKEN",
    "SPACE_KEY",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_KEY",
    "AZURE_OPENAI_EMBED_DEPLOYMENT",
    "AZURE_STORAGE_CONNECTION_STRING"
]

missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Initialize Azure clients
client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2023-05-15",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)

def load_state() -> Dict[str, Any]:
    """Load state from Azure Blob Storage"""
    try:
        blob_client = blob_service_client.get_blob_client(
            container=BLOB_CONTAINER_NAME,
            blob=STATE_BLOB_NAME
        )
        
        if blob_client.exists():
            download_stream = blob_client.download_blob()
            state_json = download_stream.readall().decode('utf-8')
            logger.info("State loaded from Azure Blob Storage")
            return json.loads(state_json)
        else:
            logger.info("No existing state found, creating new state")
            return {"indexed_pages": {}, "last_run": None, "index_initialized": False}
    except Exception as e:
        logger.error(f"Error loading state from blob storage: {e}")
        return {"indexed_pages": {}, "last_run": None, "index_initialized": False}

def save_state(state: Dict[str, Any]):
    """Save state to Azure Blob Storage"""
    try:
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        if not container_client.exists():
            container_client.create_container()
            logger.info(f"Created blob container: {BLOB_CONTAINER_NAME}")
        
        blob_client = blob_service_client.get_blob_client(
            container=BLOB_CONTAINER_NAME,
            blob=STATE_BLOB_NAME
        )
        
        state_json = json.dumps(state, indent=2)
        blob_client.upload_blob(state_json, overwrite=True)
        logger.info("State saved to Azure Blob Storage")
    except Exception as e:
        logger.error(f"Error saving state to blob storage: {e}")
        raise

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
        logger.error(f"Embedding failed: {e}")
        return [[0.0] * 1536 for _ in texts]

def fix_confluence_url(base_url: str, webui_path: str, space_key: str, page_id: str) -> str:
    """Ensure Confluence URL includes /wiki/ in the path"""
    base = base_url.rstrip('/')
    if webui_path:
        if webui_path.startswith("/"):
            if "/wiki" not in base and webui_path.startswith("/spaces"):
                return f"{base}/wiki{webui_path}"
            else:
                return f"{base}{webui_path}"
        else:
            return urljoin(base, webui_path)
    else:
        if "/wiki" in base:
            return f"{base}/spaces/{space_key}/pages/{page_id}"
        else:
            return f"{base}/wiki/spaces/{space_key}/pages/{page_id}"

def ensure_index_exists():
    idx_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=AzureKeyCredential(AZURE_SEARCH_KEY))
    existing = [n for n in idx_client.list_index_names()]
    if AZURE_SEARCH_INDEX in existing:
        logger.info(f"Index exists: {AZURE_SEARCH_INDEX}")
        return

    sample_dim = len(embed_texts(["hello world"])[0])
    logger.info(f"Creating index with vector dim: {sample_dim}")

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
        SimpleField(name="has_video", type=SearchFieldDataType.Boolean, filterable=True),
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
    logger.info(f"Index created: {AZURE_SEARCH_INDEX}")

def get_doc_client() -> SearchClient:
    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )

def upsert_documents(docs: List[Dict[str, Any]]):
    if not docs:
        return
    doc_client = get_doc_client()
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i+BATCH_SIZE]
        doc_client.upload_documents(documents=batch)
        logger.info(f"Uploaded batch {i//BATCH_SIZE + 1} size {len(batch)}")

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
        logger.info(f"Deleted {len(batch_ids)} docs for page {page_id}")

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

def run_ingest():
    """Main ingestion function"""
    logger.info("Starting Confluence ingestion process")
    
    state = load_state()
    ensure_index_exists()
    state["index_initialized"] = True

    # Fetch all pages
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

    logger.info(f"Pages found: {len(pages)}")
    current_versions = {p["id"]: p["version"]["number"] for p in pages}

    # Detect deletions
    previously_indexed = state.get("indexed_pages", {})
    deleted = [pid for pid in previously_indexed.keys() if pid not in current_versions]
    if deleted:
        logger.info(f"Deleted pages detected: {len(deleted)}")
        for pid in deleted:
            delete_docs_by_page_id(pid)
            state["indexed_pages"].pop(pid, None)

    # Detect new or changed pages
    to_update = []
    for p in pages:
        pid = p["id"]
        ver = p["version"]["number"]
        if pid not in previously_indexed or previously_indexed.get(pid) != ver:
            to_update.append(pid)

    logger.info(f"Pages to update (new/changed): {len(to_update)}")

    all_docs = []
    for pid in to_update:
        try:
            page = fetch_page(pid)
            title = page.get("title", "")
            
            links = page.get("_links", {})
            webui = links.get("webui", "")
            url = fix_confluence_url(CONFLUENCE_BASE, webui, SPACE_KEY, pid)

            storage = page.get("body", {}).get("storage", {}).get("value", "")
            text = convert_storage_to_text(storage)
            has_video = has_video_content(storage)

            chunks = chunk_text(text)
            labels = []
            if page.get("metadata", {}).get("labels"):
                labels = [l.get("name") for l in page["metadata"]["labels"].get("results", [])]

            last_modified = page.get("version", {}).get("when")
            version_num = page.get("version", {}).get("number", 1)

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
                        "has_video": has_video,
                        "vector": embeddings[j]
                    }
                    all_docs.append(doc)
                    
            logger.info(f"Processed page: {title} ({pid})")
        except Exception as e:
            logger.error(f"Error processing page {pid}: {e}")
            continue

    if all_docs:
        upsert_documents(all_docs)

    for pid in to_update:
        state["indexed_pages"][pid] = current_versions.get(pid)

    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_state(state)
    
    logger.info(f"Ingestion complete. Total docs indexed: {len(all_docs)}")
    logger.info(f"Total pages tracked: {len(state['indexed_pages'])}")

if __name__ == "__main__":
    try:
        run_ingest()
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise
