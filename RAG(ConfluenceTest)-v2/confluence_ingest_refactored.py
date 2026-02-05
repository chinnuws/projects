from dotenv import load_dotenv
load_dotenv()

import os
import json
import hashlib
import requests
from typing import List
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

# ============================================================
# Configuration (validated & casted)
# ============================================================
required_envs = [
    "CONFLUENCE_BASE_URL",
    "CONFLUENCE_USERNAME",
    "CONFLUENCE_API_TOKEN",
    "CONFLUENCE_SPACE_KEY",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_KEY",
    "AZURE_SEARCH_INDEX",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_KEY",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
]

for env in required_envs:
    if not os.getenv(env):
        raise RuntimeError(f"❌ Missing required environment variable: {env}")

CONFLUENCE_BASE_URL = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
CONFLUENCE_USERNAME = os.environ["CONFLUENCE_USERNAME"]
CONFLUENCE_API_TOKEN = os.environ["CONFLUENCE_API_TOKEN"]
CONFLUENCE_SPACE_KEY = os.environ["CONFLUENCE_SPACE_KEY"]
SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_KEY = os.environ["AZURE_SEARCH_KEY"]
INDEX_NAME = os.environ["AZURE_SEARCH_INDEX"]
AOAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AOAI_KEY = os.environ["AZURE_OPENAI_KEY"]
AOAI_EMBED_DEPLOYMENT = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]

SSL_CERT_PATH = os.getenv("SSL_CERT_PATH", "confluence.crt")
STATE_FILE = "confluence_state.json"
CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "3000"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "400"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "8"))
VECTOR_DIMENSIONS = int(os.getenv("VECTOR_DIMENSIONS", "1536"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "500"))

# ============================================================
# Clients
# ============================================================
aoai = AzureOpenAI(
    api_key=AOAI_KEY,
    azure_endpoint=AOAI_ENDPOINT,
    api_version="2024-02-15-preview",
)

index_client = SearchIndexClient(
    SEARCH_ENDPOINT,
    AzureKeyCredential(SEARCH_KEY),
)

search_client = SearchClient(
    SEARCH_ENDPOINT,
    INDEX_NAME,
    AzureKeyCredential(SEARCH_KEY),
)

# ============================================================
# Utilities
# ============================================================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = start + CHUNK_MAX_CHARS
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP_CHARS
        if start < 0:
            start = 0
    return chunks

def embed_texts(texts: List[str]) -> List[List[float]]:
    vectors = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        print(f"🧠 Embedding batch {i // BATCH_SIZE + 1} ({len(batch)} chunks)")
        resp = aoai.embeddings.create(
            model=AOAI_EMBED_DEPLOYMENT,
            input=batch,
            timeout=60,
        )
        vectors.extend([d.embedding for d in resp.data])
    return vectors

# ============================================================
# Confluence Fetch (SPACE-SCOPED)
# ============================================================
def fetch_pages():
    print(f"📥 Fetching pages from Confluence space '{CONFLUENCE_SPACE_KEY}'")
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    params = {
        "spaceKey": CONFLUENCE_SPACE_KEY,
        "limit": 50,
        "expand": "body.storage,version",
        "type": "page",
    }
    
    pages = []
    page_count = 0
    
    # Check if SSL cert exists
    verify_ssl = SSL_CERT_PATH if os.path.exists(SSL_CERT_PATH) else True
    
    while True:
        page_count += 1
        if page_count > MAX_PAGES:
            print("⚠️ Max page limit reached, stopping pagination")
            break
        
        print(f"➡️ Fetching: {url}")
        resp = requests.get(
            url,
            params=params,
            auth=(CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN),
            verify=verify_ssl,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        
        batch = data.get("results", [])
        pages.extend(batch)
        print(f"📄 Pages fetched so far: {len(pages)}")
        
        next_link = data.get("_links", {}).get("next")
        if not next_link:
            break
        
        url = CONFLUENCE_BASE_URL + next_link
        params = None  # next already includes params
    
    return pages

# ============================================================
# Index (vector-only, SDK-safe)
# ============================================================
def ensure_index():
    try:
        index_client.get_index(INDEX_NAME)
        print("ℹ️ Index already exists")
        return
    except Exception:
        pass
    
    print("🆕 Creating Azure Search index")
    
    fields = [
        SearchField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(name="page_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="title", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="url", type=SearchFieldDataType.String),
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIMENSIONS,
            vector_search_profile_name="vector-profile",
        ),
    ]
    
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw",
            )
        ],
    )
    
    index = SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
    )
    
    index_client.create_index(index)
    print("✅ Index created")

# ============================================================
# Main
# ============================================================
def run():
    print("🚀 Ingestion started")
    ensure_index()
    
    state = load_state()
    pages = fetch_pages()
    
    docs_to_upload = []
    
    for page in pages:
        page_id = page["id"]
        version = page["version"]["number"]
        title = page["title"]
        content = page["body"]["storage"]["value"]
        
        # ✅ FIXED: Correct URL construction (no duplicate /wiki)
        base = CONFLUENCE_BASE_URL.rstrip("/")
        if base.endswith("/wiki"):
            # Already has /wiki, don't add it again
            page_url = f"{base}/spaces/{CONFLUENCE_SPACE_KEY}/pages/{page_id}"
        else:
            # Doesn't have /wiki, add it
            page_url = f"{base}/wiki/spaces/{CONFLUENCE_SPACE_KEY}/pages/{page_id}"
        
        print(f"🔹 Processing page {page_id} | v{version} | URL: {page_url}")
        
        if state.get(page_id) == version:
            print(" ↳ Skipped (unchanged)")
            continue
        
        chunks = chunk_text(content)
        vectors = embed_texts(chunks)
        
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            doc_id = hashlib.sha1(f"{page_id}-{i}".encode()).hexdigest()
            docs_to_upload.append({
                "id": doc_id,
                "page_id": page_id,
                "title": title,
                "url": page_url,
                "content": chunk,
                "content_vector": vector,
            })
        
        state[page_id] = version
    
    print(f"📤 Uploading {len(docs_to_upload)} documents")
    for i in range(0, len(docs_to_upload), 500):
        batch = docs_to_upload[i : i + 500]
        search_client.upload_documents(batch)
        print(f" ↳ Uploaded {i + len(batch)}")
    
    save_state(state)
    print("✅ Ingestion complete")

if __name__ == "__main__":
    run()
