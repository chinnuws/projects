import os
import uuid
import logging
import requests
from typing import List
from dotenv import load_dotenv

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    VectorSearchAlgorithmConfiguration,
)

from openai import AzureOpenAI

# --------------------------------------------------
# Load env
# --------------------------------------------------
load_dotenv()

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL").rstrip("/")
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "3000"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "400"))

SSL_VERIFY = os.getenv("CONFLUENCE_CA_CERT", True)

logging.basicConfig(level=logging.INFO)

# --------------------------------------------------
# Clients
# --------------------------------------------------
openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
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
# Helpers
# --------------------------------------------------
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


def embed(text: str) -> List[float]:
    resp = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=text,
    )
    return resp.data[0].embedding


# --------------------------------------------------
# Azure Search Index (vector only)
# --------------------------------------------------
def create_index():
    try:
        index_client.get_index(AZURE_SEARCH_INDEX)
        logging.info("Index already exists")
        return
    except Exception:
        pass

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="page_id", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="title", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
        SimpleField(name="url", type=SearchFieldDataType.String, filterable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536,
            vector_search_configuration="vector-config",
        ),
    ]

    vector_search = VectorSearch(
        algorithm_configurations=[
            VectorSearchAlgorithmConfiguration(
                name="vector-config",
                kind="hnsw",
            )
        ]
    )

    index = SearchIndex(
        name=AZURE_SEARCH_INDEX,
        fields=fields,
        vector_search=vector_search,
    )

    index_client.create_index(index)
    logging.info("Index created")


# --------------------------------------------------
# Confluence fetch (space-scoped)
# --------------------------------------------------
def fetch_pages():
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    params = {
        "spaceKey": CONFLUENCE_SPACE_KEY,
        "expand": "body.storage",
        "type": "page",
        "limit": 50,
    }

    pages = []

    while True:
        logging.info(f"Fetching: {url}")
        resp = requests.get(
            url,
            auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN),
            params=params,
            verify=SSL_VERIFY,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        pages.extend(data.get("results", []))

        next_link = data.get("_links", {}).get("next")
        if not next_link:
            break

        url = CONFLUENCE_BASE_URL + next_link
        params = None

    return pages


# --------------------------------------------------
# Run ingestion
# --------------------------------------------------
def run():
    logging.info("🚀 Ingestion started")

    create_index()
    pages = fetch_pages()
    logging.info(f"Fetched {len(pages)} pages")

    buffer = []

    for page in pages:
        page_id = page["id"]
        title = page["title"]
        html = page["body"]["storage"]["value"]
        text = html.replace("<", " ").replace(">", " ")
        url = CONFLUENCE_BASE_URL + page["_links"]["webui"]

        chunks = chunk_text(text)

        for chunk in chunks:
            buffer.append({
                "id": str(uuid.uuid4()),
                "page_id": page_id,
                "title": title,
                "content": chunk,
                "url": url,
                "content_vector": embed(chunk),
            })

        if len(buffer) >= 100:
            search_client.upload_documents(buffer)
            buffer.clear()

    if buffer:
        search_client.upload_documents(buffer)

    logging.info("✅ Ingestion completed")


if __name__ == "__main__":
    run()
