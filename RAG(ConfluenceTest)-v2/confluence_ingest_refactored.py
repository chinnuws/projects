import os
import hashlib
import requests
from dotenv import load_dotenv
from typing import List
from bs4 import BeautifulSoup

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
)

from openai import AzureOpenAI

# ============================================================
# ENV
# ============================================================
load_dotenv()

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_CERT = os.getenv("CONFLUENCE_CERT")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

CHUNK_MAX_CHARS = 3000
CHUNK_OVERLAP_CHARS = 400
VECTOR_DIMENSIONS = 1536
BATCH_SIZE = 16

# ============================================================
# CLIENTS
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

aoai = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
)

# ============================================================
# INDEX
# ============================================================
def create_index():
    try:
        index_client.get_index(AZURE_SEARCH_INDEX)
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
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=VECTOR_DIMENSIONS,
                vector_search_configuration="vector-config",
            ),
        ],
        vector_search=VectorSearch(
            algorithm_configurations=[
                HnswAlgorithmConfiguration(
                    name="vector-config",
                    metric="cosine",
                    m=4,
                    ef_construction=400,
                    ef_search=500,
                )
            ]
        ),
    )

    index_client.create_index(index)

# ============================================================
# HTML → CLEAN TEXT (TABLE AWARE)
# ============================================================
def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Convert tables to readable text
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            rows.append(" | ".join(cells))
        table.replace_with("\nTABLE:\n" + "\n".join(rows) + "\n")

    return soup.get_text(separator="\n", strip=True)

# ============================================================
# FETCH PAGES (WITH ANCESTORS)
# ============================================================
def fetch_pages():
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    params = {
        "spaceKey": CONFLUENCE_SPACE_KEY,
        "expand": "body.storage,ancestors",
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
# CHUNKING
# ============================================================
def chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_MAX_CHARS
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP_CHARS
    return chunks

# ============================================================
# EMBEDDINGS
# ============================================================
def embed_texts(texts: List[str]) -> List[List[float]]:
    vectors = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        resp = aoai.embeddings.create(
            model=AZURE_OPENAI_EMBED_DEPLOYMENT,
            input=batch,
        )
        vectors.extend([d.embedding for d in resp.data])
    return vectors

# ============================================================
# RUN
# ============================================================
def run():
    create_index()
    pages = fetch_pages()

    docs = []

    for page in pages:
        page_id = page["id"]
        title = page["title"]

        ancestors = page.get("ancestors", [])
        hierarchy = " > ".join(a["title"] for a in ancestors)

        html = page["body"]["storage"]["value"]
        clean_text = html_to_text(html)

        if hierarchy:
            clean_text = f"Page Hierarchy: {hierarchy}\nPage Title: {title}\n\n{clean_text}"

        url = f"{CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId={page_id}"

        chunks = chunk_text(clean_text)
        vectors = embed_texts(chunks)

        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            doc_id = hashlib.sha1(f"{page_id}-{i}".encode()).hexdigest()
            docs.append({
                "id": doc_id,
                "page_id": page_id,
                "title": title,
                "content": chunk,
                "content_vector": vector,
                "url": url,
            })

    for i in range(0, len(docs), 500):
        search_client.upload_documents(docs[i:i + 500])

    print("Ingestion completed successfully")

if __name__ == "__main__":
    run()
