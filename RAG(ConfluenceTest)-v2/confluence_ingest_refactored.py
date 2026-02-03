import os
import json
import time
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
    VectorSearchProfile
)
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

# =========================
# Configuration
# =========================

SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_KEY = os.environ["AZURE_SEARCH_KEY"]
INDEX_NAME = os.environ["AZURE_SEARCH_INDEX"]

AOAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AOAI_KEY = os.environ["AZURE_OPENAI_KEY"]
AOAI_EMBED_DEPLOYMENT = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]

CONFLUENCE_BASE_URL = os.environ["CONFLUENCE_BASE_URL"]
CONFLUENCE_USERNAME = os.environ["CONFLUENCE_USERNAME"]
CONFLUENCE_API_TOKEN = os.environ["CONFLUENCE_API_TOKEN"]

STATE_FILE = "confluence_state.json"
SSL_CERT_PATH = "confluence.crt"

CHUNK_MAX_CHARS = 3000
CHUNK_OVERLAP_CHARS = 400
BATCH_SIZE = 32
VECTOR_DIMENSIONS = 1536   # text-embedding-3-large

# =========================
# Clients
# =========================

aoai = AzureOpenAI(
    api_key=AOAI_KEY,
    azure_endpoint=AOAI_ENDPOINT,
    api_version="2024-02-15-preview"
)

index_client = SearchIndexClient(
    SEARCH_ENDPOINT,
    AzureKeyCredential(SEARCH_KEY)
)

search_client = SearchClient(
    SEARCH_ENDPOINT,
    INDEX_NAME,
    AzureKeyCredential(SEARCH_KEY)
)

# =========================
# Helpers
# =========================

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_MAX_CHARS
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - CHUNK_OVERLAP_CHARS
        if start < 0:
            start = 0
    return chunks

def embed_texts(texts: List[str]) -> List[List[float]]:
    embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        resp = aoai.embeddings.create(
            model=AOAI_EMBED_DEPLOYMENT,
            input=batch
        )
        embeddings.extend([d.embedding for d in resp.data])
    return embeddings

# =========================
# Confluence Fetch
# =========================

def fetch_pages():
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    params = {
        "limit": 50,
        "expand": "body.storage,version"
    }

    pages = []
    while True:
        resp = requests.get(
            url,
            params=params,
            auth=(CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN),
            verify=SSL_CERT_PATH
        )
        resp.raise_for_status()
        data = resp.json()

        pages.extend(data["results"])

        if "_links" in data and "next" in data["_links"]:
            url = CONFLUENCE_BASE_URL + data["_links"]["next"]
            params = None
        else:
            break

    return pages

# =========================
# Index Creation (NO semantic)
# =========================

def ensure_index():
    try:
        index_client.get_index(INDEX_NAME)
        print("ℹ️ Index already exists")
        return
    except Exception:
        pass

    fields = [
        SearchField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(name="page_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="title", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIMENSIONS,
            vector_search_profile_name="vector-profile"
        )
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="hnsw")
        ],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw"
            )
        ]
    )

    index = SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=vector_search
    )

    index_client.create_index(index)
    print("✅ Index created (no semantic settings)")

# =========================
# Main Ingest
# =========================

def run():
    ensure_index()

    state = load_state()
    pages = fetch_pages()
    docs_to_upload = []

    for page in pages:
        page_id = page["id"]
        version = page["version"]["number"]
        title = page["title"]
        content = page["body"]["storage"]["value"]

        state_key = f"{page_id}:{version}"
        if state.get(page_id) == version:
            continue

        chunks = chunk_text(content)
        embeddings = embed_texts(chunks)

        for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            doc_id = hashlib.sha1(f"{page_id}-{i}".encode()).hexdigest()

            docs_to_upload.append({
                "id": doc_id,
                "page_id": page_id,
                "title": title,
                "content": chunk,
                "content_vector": vector
            })

        state[page_id] = version

    if docs_to_upload:
        search_client.upload_documents(docs_to_upload)
        print(f"✅ Uploaded {len(docs_to_upload)} documents")

    save_state(state)
    print("✅ Ingestion complete")

# =========================

if __name__ == "__main__":
    run()
