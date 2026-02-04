import os
import time
import json
import uuid
import requests
from typing import List
from bs4 import BeautifulSoup

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
)

from openai import AzureOpenAI

# -------------------------
# ENV
# -------------------------
AZURE_SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
AZURE_SEARCH_KEY = os.environ["AZURE_SEARCH_KEY"]
AZURE_SEARCH_INDEX = os.environ["AZURE_SEARCH_INDEX"]

AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_KEY"]
AZURE_OPENAI_EMBED_DEPLOYMENT = os.environ["AZURE_OPENAI_EMBED_DEPLOYMENT"]
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15")

CONFLUENCE_BASE_URL = os.environ["CONFLUENCE_BASE_URL"]
CONFLUENCE_USER = os.environ["CONFLUENCE_USER"]
CONFLUENCE_API_TOKEN = os.environ["CONFLUENCE_API_TOKEN"]
CONFLUENCE_SPACE_KEY = os.environ["CONFLUENCE_SPACE_KEY"]

CHUNK_MAX_CHARS = 3000
CHUNK_OVERLAP_CHARS = 400
BATCH_SIZE = 32

# -------------------------
# CLIENTS
# -------------------------
openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

index_client = SearchIndexClient(
    AZURE_SEARCH_ENDPOINT,
    AzureKeyCredential(AZURE_SEARCH_KEY)
)

search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_INDEX,
    AzureKeyCredential(AZURE_SEARCH_KEY)
)

# -------------------------
# INDEX
# -------------------------
def ensure_index():
    existing = [idx.name for idx in index_client.list_indexes()]
    if AZURE_SEARCH_INDEX in existing:
        print("Index exists. Skipping creation.")
        return

    fields = [
        SimpleField(name="id", type="Edm.String", key=True),
        SearchableField(name="content", type="Edm.String"),
        SimpleField(name="content_vector", type="Collection(Edm.Single)", searchable=True),
        SearchableField(name="title", type="Edm.String"),
        SimpleField(name="url", type="Edm.String"),
        SimpleField(name="space", type="Edm.String"),
        SimpleField(name="page_id", type="Edm.String"),
        SimpleField(name="parent_path", type="Edm.String"),
    ]

    index = SearchIndex(
        name=AZURE_SEARCH_INDEX,
        fields=fields,
        vector_search={
            "algorithmConfigurations": [
                {
                    "name": "default",
                    "kind": "hnsw"
                }
            ]
        }
    )

    index_client.create_index(index)
    print("Index created.")

# -------------------------
# CONFLUENCE
# -------------------------
def fetch_pages():
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    start = 0
    pages = []

    while True:
        params = {
            "spaceKey": CONFLUENCE_SPACE_KEY,
            "limit": 50,
            "start": start,
            "expand": "body.storage,ancestors"
        }
        r = requests.get(
            url,
            params=params,
            auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN),
            timeout=60,
            verify=False  # matches your earlier working behavior
        )
        r.raise_for_status()
        data = r.json()

        pages.extend(data["results"])

        if data.get("_links", {}).get("next"):
            start += 50
        else:
            break

    print(f"Fetched {len(pages)} pages")
    return pages

# -------------------------
# HTML → TEXT (TABLE SAFE)
# -------------------------
def extract_text_with_tables(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    tables_output = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            tables_output.append("Table:\n" + "\n".join(rows))
        table.decompose()

    body_text = soup.get_text(separator="\n", strip=True)
    return body_text + "\n\n" + "\n\n".join(tables_output)

# -------------------------
# HIERARCHY
# -------------------------
def build_parent_path(page) -> str:
    ancestors = page.get("ancestors", [])
    return " > ".join([a["title"] for a in ancestors])

# -------------------------
# CHUNKING
# -------------------------
def chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_MAX_CHARS
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - CHUNK_OVERLAP_CHARS
    return chunks

# -------------------------
# EMBEDDINGS
# -------------------------
def embed_texts(texts: List[str]) -> List[List[float]]:
    resp = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=texts
    )
    return [d.embedding for d in resp.data]

# -------------------------
# INGEST
# -------------------------
def ingest():
    ensure_index()
    pages = fetch_pages()
    docs = []

    for page in pages:
        html = page["body"]["storage"]["value"]
        clean_text = extract_text_with_tables(html)

        parent_path = build_parent_path(page)

        full_text = f"""
Title: {page['title']}
Hierarchy: {parent_path}
---------------------
{clean_text}
"""

        chunks = chunk_text(full_text)
        vectors = embed_texts(chunks)

        page_url = f"{CONFLUENCE_BASE_URL}{page['_links']['webui']}"

        for chunk, vector in zip(chunks, vectors):
            docs.append({
                "id": str(uuid.uuid4()),
                "content": chunk,
                "content_vector": vector,
                "title": page["title"],
                "url": page_url,
                "space": CONFLUENCE_SPACE_KEY,
                "page_id": page["id"],
                "parent_path": parent_path
            })

        if len(docs) >= BATCH_SIZE:
            search_client.upload_documents(docs)
            docs.clear()
            time.sleep(0.5)

    if docs:
        search_client.upload_documents(docs)

    print("Ingestion completed successfully.")

# -------------------------
if __name__ == "__main__":
    print("Ingestion started")
    ingest()
