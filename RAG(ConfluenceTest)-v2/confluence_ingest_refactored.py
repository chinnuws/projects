import os
import json
import time
import uuid
import requests
import logging
from typing import List

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
from dotenv import load_dotenv

# --------------------------------------------------
# Load env
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
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "3000"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "400"))

VERIFY_SSL = os.getenv("CONFLUENCE_CA_CERT", True)

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

logging.basicConfig(level=logging.INFO)


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + CHUNK_MAX_CHARS
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - CHUNK_OVERLAP_CHARS
        if start < 0:
            start = 0

    return chunks


def embed_text(text: str) -> List[float]:
    resp = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=text
    )
    return resp.data[0].embedding


# --------------------------------------------------
# Azure Search Index
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
                kind="hnsw"
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
# Confluence Fetch
# --------------------------------------------------
def fetch_pages():
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    params = {
        "spaceKey": CONFLUENCE_SPACE_KEY,
        "expand": "body.storage",
        "limit": 50,
    }

    pages = []

    while True:
        logging.info(f"Fetching: {url}")
        resp = requests.get(
            url,
            auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN),
            params=params,
            verify=VERIFY_SSL,
            timeout=60,
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


# --------------------------------------------------
# Run
# --------------------------------------------------
def run():
    logging.info("🚀 Ingestion started")

    create_index()

    pages = fetch_pages()
    logging.info(f"Fetched {len(pages)} pages")

    docs = []

    for page in pages:
        page_id = page["id"]
        title = page["title"]
        html = page["body"]["storage"]["value"]
        text = html.replace("<", " ").replace(">", " ")
        url = CONFLUENCE_BASE_URL + page["_links"]["webui"]

        chunks = chunk_text(text)

        for chunk in chunks:
            embedding = embed_text(chunk)
            docs.append({
                "id": str(uuid.uuid4()),
                "page_id": page_id,
                "title": title,
                "content": chunk,
                "url": url,
                "content_vector": embedding,
            })

        if len(docs) >= 100:
            search_client.upload_documents(docs)
            docs.clear()

    if docs:
        search_client.upload_documents(docs)

    logging.info("✅ Ingestion completed")


if __name__ == "__main__":
    run()
