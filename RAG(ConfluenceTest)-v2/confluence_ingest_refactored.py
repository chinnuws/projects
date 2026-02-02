"""
confluence_ingest_refactored.py

High-quality Confluence → Azure AI Search ingestion
Compatible with azure-search-documents 11.6.x
Semantic reranker enabled (dict-based config)
"""

import os
import re
import json
import time
import logging
from typing import List
from html import unescape
from dotenv import load_dotenv
import requests

# Azure Search
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

# Azure OpenAI
from openai import AzureOpenAI

# --------------------------------------------------
# ENV
# --------------------------------------------------

load_dotenv()
logging.basicConfig(level=logging.INFO)

CONFLUENCE_BASE = os.getenv("CONFLUENCE_BASE")
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")

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

# --------------------------------------------------
# CLIENTS
# --------------------------------------------------

aoai = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2023-05-15",
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
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
# CONFLUENCE
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
    r = requests.get(url, params=params, auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN))
    r.raise_for_status()
    return r.json()

def fetch_page(page_id: str):
    url = f"{CONFLUENCE_BASE}/rest/api/content/{page_id}"
    params = {"expand": "body.storage,version,metadata.labels,links.webui"}
    r = requests.get(url, params=params, auth=(CONFLUENCE_USER, CONFLUENCE_API_TOKEN))
    r.raise_for_status()
    return r.json()

# --------------------------------------------------
# TEXT PROCESSING
# --------------------------------------------------

def html_to_text(html: str) -> str:
    html = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", html)
    html = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", html)
    html = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", html)

    html = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", html)

    html = re.sub(r"<tr[^>]*>(.*?)</tr>", r"\n\1", html)
    html = re.sub(r"<th[^>]*>(.*?)</th>", r" \1 |", html)
    html = re.sub(r"<td[^>]*>(.*?)</td>", r" \1 |", html)

    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()

def smart_chunk(text: str) -> List[str]:
    sections = re.split(r"\n#{1,3}\s+", text)
    chunks = []

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue

        if len(sec) <= CHUNK_MAX_CHARS:
            chunks.append(sec)
        else:
            i = 0
            while i < len(sec):
                end = min(i + CHUNK_MAX_CHARS, len(sec))
                chunks.append(sec[i:end])
                i += CHUNK_MAX_CHARS - CHUNK_OVERLAP_CHARS

    return chunks

# --------------------------------------------------
# EMBEDDINGS
# --------------------------------------------------

def embed(texts: List[str]) -> List[List[float]]:
    resp = aoai.embeddings.create(
        model=EMBED_DEPLOYMENT,
        input=texts,
    )
    return [r.embedding for r in resp.data]

# --------------------------------------------------
# INDEX CREATION (SDK-SAFE)
# --------------------------------------------------

def ensure_index():
    if AZURE_SEARCH_INDEX in index_client.list_index_names():
        logging.info("Search index exists")
        return

    dim = len(embed(["hello world"])[0])

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
    logging.info("Created index with semantic reranker enabled")

# --------------------------------------------------
# INGEST
# --------------------------------------------------

def run():
    ensure_index()
    state = load_state()

    pages = []
    start = 0
    while True:
        batch = list_pages(start=start)
        results = batch.get("results", [])
        if not results:
            break
        pages.extend(results)
        start += len(results)

    for p in pages:
        pid = p["id"]
        version = p["version"]["number"]

        if state["indexed_pages"].get(pid) == version:
            continue

        page = fetch_page(pid)
        title = page["title"]
        html = page["body"]["storage"]["value"]

        text = html_to_text(html)
        chunks = smart_chunk(text)

        url = f"{CONFLUENCE_BASE}{page['_links']['webui']}"

        contextual_chunks = [
            f"Confluence Space: {SPACE_KEY}\nPage Title: {title}\nContent:\n{c}"
            for c in chunks
        ]

        embeddings = embed(contextual_chunks)

        docs = []
        for i, (chunk, vec) in enumerate(zip(chunks, embeddings)):
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
    logging.info("Ingestion complete")

# --------------------------------------------------

if __name__ == "__main__":
    run()
