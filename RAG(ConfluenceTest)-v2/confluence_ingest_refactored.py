import os
import time
import uuid
import requests
from typing import List
from bs4 import BeautifulSoup

from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile
)
from azure.core.credentials import AzureKeyCredential

from openai import AzureOpenAI
from dotenv import load_dotenv

# --------------------------------------------------
# ENV
# --------------------------------------------------
load_dotenv()

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

CHUNK_MAX_CHARS = 3000
CHUNK_OVERLAP_CHARS = 400
BATCH_SIZE = 16

# --------------------------------------------------
# CLIENTS
# --------------------------------------------------
openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

index_client = SearchIndexClient(
    AZURE_SEARCH_ENDPOINT,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_INDEX,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

# --------------------------------------------------
# INDEX
# --------------------------------------------------
def create_index():
    print("🧱 Creating Azure Search index...")

    try:
        index_client.delete_index(AZURE_SEARCH_INDEX)
        print("⚠️ Existing index deleted")
    except Exception:
        pass

    fields = [
        SimpleField(name="id", type="Edm.String", key=True),
        SearchableField(name="title", type="Edm.String"),
        SearchableField(name="content", type="Edm.String"),
        SimpleField(name="url", type="Edm.String"),
        SimpleField(name="page_id", type="Edm.String"),
        SimpleField(name="parent_title", type="Edm.String"),
        SearchableField(
            name="content_vector",
            type="Collection(Edm.Single)",
            vector_search_dimensions=1536,
            vector_search_profile_name="vector-profile"
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="hnsw-config")
        ],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw-config"
            )
        ]
    )

    index = SearchIndex(
        name=AZURE_SEARCH_INDEX,
        fields=fields,
        vector_search=vector_search
    )

    index_client.create_index(index)
    print("✅ Index created")

# --------------------------------------------------
# CONFLUENCE
# --------------------------------------------------
def fetch_pages():
    print("📥 Fetching pages from Confluence...")
    pages = []
    start = 0
    limit = 50

    while True:
        url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
        params = {
            "spaceKey": CONFLUENCE_SPACE_KEY,
            "limit": limit,
            "start": start,
            "expand": "body.storage,ancestors"
        }

        resp = requests.get(
            url,
            params=params,
            auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN),
            verify=True,
        )
        resp.raise_for_status()

        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        pages.extend(results)
        start += limit

        print(f"   ➕ Fetched {len(pages)} pages so far")

    print(f"✅ Total pages fetched: {len(pages)}")
    return pages

# --------------------------------------------------
# HTML → TEXT
# --------------------------------------------------
def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Tables → readable text
    for table in soup.find_all("table"):
        rows = []
        for row in table.find_all("tr"):
            cols = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            rows.append(" | ".join(cols))
        table.replace_with("\n".join(rows))

    return soup.get_text("\n", strip=True)

# --------------------------------------------------
# CHUNKING
# --------------------------------------------------
def chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0

    while start < len(text):
        end = start + CHUNK_MAX_CHARS
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP_CHARS

    return chunks

# --------------------------------------------------
# EMBEDDING
# --------------------------------------------------
def embed(texts: List[str]) -> List[List[float]]:
    print(f"      🧠 Embedding {len(texts)} chunks")
    resp = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        input=texts
    )
    print("      ✅ Embeddings generated")
    return [d.embedding for d in resp.data]

# --------------------------------------------------
# INGEST
# --------------------------------------------------
def ingest():
    print("🚀 Ingestion started")
    create_index()

    pages = fetch_pages()
    docs = []

    for page in pages:
        page_id = page["id"]
        title = page["title"]
        html = page["body"]["storage"]["value"]
        url = f"{CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId={page_id}"

        ancestors = page.get("ancestors", [])
        parent_title = ancestors[-1]["title"] if ancestors else ""

        print(f"\n📄 Processing page: {title}")
        text = f"Parent: {parent_title}\nTitle: {title}\n\n{html_to_text(html)}"

        chunks = chunk_text(text)
        print(f"   ✂️ {len(chunks)} chunks created")

        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i+BATCH_SIZE]
            vectors = embed(batch)

            for chunk, vector in zip(batch, vectors):
                docs.append({
                    "id": str(uuid.uuid4()),
                    "title": title,
                    "content": chunk,
                    "url": url,
                    "page_id": page_id,
                    "parent_title": parent_title,
                    "content_vector": vector,
                })

            print(f"   📤 Uploading batch {i//BATCH_SIZE + 1}")
            search_client.upload_documents(docs)
            docs.clear()

    print("🎉 Ingestion complete")

if __name__ == "__main__":
    ingest()
