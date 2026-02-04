import os
import uuid
import requests
from dotenv import load_dotenv
from typing import List

from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    VectorField,
)
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

# ============================================================
# Load env
# ============================================================
load_dotenv()

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")  # https://your-domain.atlassian.net/wiki
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_CERT = os.getenv("CONFLUENCE_CERT")  # path to cert or None

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "3000"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "400"))
VECTOR_DIMENSIONS = int(os.getenv("VECTOR_DIMENSIONS", "1536"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))

# ============================================================
# Clients
# ============================================================
index_client = SearchIndexClient(
    AZURE_SEARCH_ENDPOINT,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

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

# ============================================================
# Index creation
# ============================================================
def create_index():
    try:
        index_client.get_index(AZURE_SEARCH_INDEX)
        print("ℹ️ Index already exists")
        return
    except Exception:
        pass

    index = SearchIndex(
        name=AZURE_SEARCH_INDEX,
        fields=[
            SimpleField(name="id", type="Edm.String", key=True),
            SimpleField(name="page_id", type="Edm.String"),
            SearchableField(name="title", type="Edm.String"),
            SearchableField(name="content", type="Edm.String"),
            SimpleField(name="url", type="Edm.String"),
            VectorField(
                name="content_vector",
                vector_search_dimensions=VECTOR_DIMENSIONS,
                vector_search_profile_name="default-vector-profile",
            ),
        ],
        vector_search={
            "algorithms": [
                {
                    "name": "hnsw-algorithm",
                    "kind": "hnsw",
                    "hnswParameters": {
                        "metric": "cosine",
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500,
                    },
                }
            ],
            "profiles": [
                {
                    "name": "default-vector-profile",
                    "algorithm": "hnsw-algorithm",
                }
            ],
        },
    )

    index_client.create_index(index)
    print("✅ Index created")

# ============================================================
# Confluence fetch
# ============================================================
def fetch_pages():
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    params = {
        "spaceKey": CONFLUENCE_SPACE_KEY,
        "expand": "body.storage",
        "limit": 50,
    }

    auth = (CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
    pages = []

    while True:
        resp = requests.get(
            url,
            params=params,
            auth=auth,
            verify=CONFLUENCE_CERT if CONFLUENCE_CERT else True,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        pages.extend(data.get("results", []))

        if "_links" in data and "next" in data["_links"]:
            url = CONFLUENCE_BASE_URL + data["_links"]["next"]
            params = None
        else:
            break

    return pages

# ============================================================
# Chunking
# ============================================================
def chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0
    length = len(text)

    while start < length:
        end = start + CHUNK_MAX_CHARS
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP_CHARS

    return chunks

# ============================================================
# Embeddings
# ============================================================
def embed(texts: List[str]) -> List[List[float]]:
    embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        resp = openai_client.embeddings.create(
            model=AZURE_OPENAI_EMBED_DEPLOYMENT,
            input=batch,
        )
        embeddings.extend([d.embedding for d in resp.data])
    return embeddings

# ============================================================
# Run ingestion
# ============================================================
def run():
    print("🚀 Ingestion started")
    create_index()

    print("📄 Fetching pages from Confluence…")
    pages = fetch_pages()

    docs = []

    for page in pages:
        page_id = page["id"]
        title = page["title"]
        content = page["body"]["storage"]["value"]
        url = f"{CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId={page_id}"

        chunks = chunk_text(content)
        vectors = embed(chunks)

        for text, vector in zip(chunks, vectors):
            docs.append({
                "id": str(uuid.uuid4()),
                "page_id": page_id,
                "title": title,
                "content": text,
                "url": url,
                "content_vector": vector,
            })

    for i in range(0, len(docs), 1000):
        search_client.upload_documents(docs[i:i + 1000])

    print(f"✅ Uploaded {len(docs)} chunks")

if __name__ == "__main__":
    run()
