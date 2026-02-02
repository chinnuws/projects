import os
import re
import json
import time
import logging
from typing import List
from html import unescape

import requests
from dotenv import load_dotenv

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
    VectorSearchProfile,
)

from openai import AzureOpenAI, RateLimitError, BadRequestError

# --------------------------------------------------
# ENV
# --------------------------------------------------

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

CONFLUENCE_BASE = os.getenv("CONFLUENCE_BASE")
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")
CONFLUENCE_CA_CERT = os.getenv("CONFLUENCE_CA_CERT")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "confluence-rag-v2")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")

STATE_FILE = "./ingest_state.json"

CHUNK_MAX_CHARS = 1800
CHUNK_OVERLAP_CHARS = 200
BATCH_SIZE = 16
MAX_EMBED_RETRIES = 5

# --------------------------------------------------
# VALIDATION
# --------------------------------------------------

if CONFLUENCE_CA_CERT and not os.path.exists(CONFLUENCE_CA_CERT):
    raise RuntimeError(f"Missing Confluence CA cert: {CONFLUENCE_CA_CERT}")

# --------------------------------------------------
# CLIENTS
# --------------------------------------------------

aoai = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version="2023-05-15",
)

index_client = SearchIndexClient(
    AZURE_SEARCH_ENDPOINT,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

doc_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_INDEX,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

# --------------------------------------------------
# STATE
# --------------------------------------------------

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {"indexed_pages": {}}

def save_state(state):
    json.dump(state, open(STATE_FILE, "w"), indent=2)

# --------------------------------------------------
# CONFLUENCE API
# --------------------------------------------------

def list_pages(start=0, limit=50):
    url = f"{CONFLUENCE_BASE}/rest/api/content"
    params = {
        "spaceKey": SPACE_KEY,
        "type": "page",
        "limit": limit,
        "start": start,
        "expand": "version",
    }
    r = requests.get(
        url,
        params=params,
        auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN),
        verify=CONFLUENCE_CA_CERT,
    )
    r.raise_for_status()
    return r.json()

def fetch_page(page_id: str):
    url = f"{CONFLUENCE_BASE}/rest/api/content/{page_id}"
    params = {"expand": "body.storage,version,links.webui"}
    r = requests.get(
        url,
        params=params,
        auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN),
        verify=CONFLUENCE_CA_CERT,
    )
    r.raise_for_status()
    return r.json()

# --------------------------------------------------
# TEXT PROCESSING
# --------------------------------------------------

def html_to_text(html: str) -> str:
    html = re.sub(
        r"<table.*?>.*?</table>",
        lambda m: "\nTABLE:\n" + re.sub(r"<[^>]+>", " ", m.group()) + "\n",
        html,
        flags=re.S,
    )

    html = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n# \1\n", html)
    html = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", html)

    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()

def chunk_text(text: str) -> List[str]:
    chunks = []
    i = 0
    while i < len(text):
        end = min(i + CHUNK_MAX_CHARS, len(text))
        chunk = text[i:end].strip()
        if len(chunk) > 20:
            chunks.append(chunk)
        i += CHUNK_MAX_CHARS - CHUNK_OVERLAP_CHARS
    return chunks

# --------------------------------------------------
# EMBEDDINGS
# --------------------------------------------------

def embed(texts: List[str]) -> List[List[float]]:
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return []

    for attempt in range(1, MAX_EMBED_RETRIES + 1):
        try:
            resp = aoai.embeddings.create(
                model=EMBED_DEPLOYMENT,
                input=texts,
            )
            return [r.embedding for r in resp.data]

        except (RateLimitError, BadRequestError):
            time.sleep(2 ** attempt)

    return []

# --------------------------------------------------
# INDEX
# --------------------------------------------------

def ensure_index():
    if AZURE_SEARCH_INDEX in index_client.list_index_names():
        return

    dim = len(embed(["hello"])[0])

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(
            name="vector-profile",
            algorithm_configuration_name="hnsw",
        )],
    )

    semantic_config = {
        "name": "default",
        "prioritizedFields": {
            "titleField": {"fieldName": "title"},
            "contentFields": [{"fieldName": "content"}],
        },
    }

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="page_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="url", type=SearchFieldDataType.String),
        SimpleField(name="space", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="version", type=SearchFieldDataType.Int32),
        SearchField(
            name="vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            vector_search_dimensions=dim,
            vector_search_profile_name="vector-profile",
        ),
    ]

    index = SearchIndex(
        name=AZURE_SEARCH_INDEX,
        fields=fields,
        vector_search=vector_search,
        semantic_configurations=[semantic_config],
    )

    index_client.create_index(index)

# --------------------------------------------------
# RUN
# --------------------------------------------------

def run():
    ensure_index()
    state = load_state()

    start = 0
    while True:
        batch = list_pages(start=start)
        pages = batch.get("results", [])
        if not pages:
            break
        start += len(pages)

        for p in pages:
            pid = p["id"]
            version = p["version"]["number"]

            if state["indexed_pages"].get(pid) == version:
                continue

            page = fetch_page(pid)
            title = page["title"]
            url = f"{CONFLUENCE_BASE}{page['_links']['webui']}"

            text = html_to_text(page["body"]["storage"]["value"])
            chunks = chunk_text(text)

            if not chunks:
                continue

            contextual = [
                f"Space: {SPACE_KEY}\nTitle: {title}\nContent:\n{c}"
                for c in chunks
            ]

            vectors = embed(contextual)
            if not vectors:
                continue

            docs = []
            for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
                docs.append({
                    "id": f"{pid}_{i}",
                    "page_id": pid,
                    "title": title,
                    "content": chunk,
                    "url": url,
                    "space": SPACE_KEY,
                    "version": version,
                    "vector": vec,
                })

            for i in range(0, len(docs), BATCH_SIZE):
                doc_client.upload_documents(docs[i:i + BATCH_SIZE])

            state["indexed_pages"][pid] = version
            logging.info(f"Indexed: {title}")

    save_state(state)
    logging.info("Ingestion completed")

if __name__ == "__main__":
    run()
