#!/usr/bin/env python3
"""
ingest_worker.py

Run from Kubernetes CronJob. Environment variables (from k8s secrets/configmap):
  CONFLUENCE_BASE_URL, SPACE_KEY, SCRAPE_START_PATH, COG_SEARCH_ENDPOINT,
  COG_SEARCH_ADMIN_KEY, AZ_OPENAI_API_KEY, AZ_OPENAI_ENDPOINT, AZ_OPENAI_DEPLOYMENT,
  CHUNK_SIZE, CHUNK_OVERLAP, SCRAPE_MAX_PAGES, USE_BLOB

This script:
 - Crawls Confluence pages under the given SPACE_KEY
 - Extracts text, computes content hash
 - Checks Cognitive Search for contentHash to skip unchanged pages
 - Creates embeddings using Azure OpenAI embeddings endpoint
 - Uploads chunk documents to Cognitive Search via REST / SDK
"""
import os
import re
import time
import hashlib
import logging
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from typing import List

# Azure Search SDK
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex, SimpleField, SearchableField, VectorSearch, VectorSearchAlgorithmConfiguration, VectorSearchAlgorithm, SearchFieldDataType, ComplexField

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest")

# Load environment
BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
SPACE_KEY = os.getenv("SPACE_KEY")
START_PATH = os.getenv("SCRAPE_START_PATH") or f"/display/{SPACE_KEY}"
COG_ENDPOINT = os.getenv("COG_SEARCH_ENDPOINT")
COG_KEY = os.getenv("COG_SEARCH_ADMIN_KEY")
COG_INDEX = os.getenv("COG_SEARCH_INDEX", "confluence-index")
AZ_OPENAI_KEY = os.getenv("AZ_OPENAI_API_KEY")
AZ_OPENAI_ENDPOINT = os.getenv("AZ_OPENAI_ENDPOINT")
AZ_OPENAI_DEPLOYMENT = os.getenv("AZ_OPENAI_DEPLOYMENT")  # embedding deployment name
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
SCRAPE_MAX_PAGES = int(os.getenv("SCRAPE_MAX_PAGES", "2000"))
USE_BLOB = os.getenv("USE_BLOB", "false").lower() == "true"
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_PASS = os.getenv("CONFLUENCE_PASS")

session = requests.Session()
if CONFLUENCE_USER and CONFLUENCE_PASS:
    session.auth = (CONFLUENCE_USER, CONFLUENCE_PASS)

# Prepare Azure Search client
search_client = SearchClient(endpoint=COG_ENDPOINT, index_name=COG_INDEX, credential=AzureKeyCredential(COG_KEY))

def norm_url(href: str) -> str:
    return urljoin(BASE_URL, href)

def same_space_url(url: str) -> bool:
    # Accept URLs that contain /display/SPACE_KEY/ or /spaces/SPACE_KEY/
    return f"/display/{SPACE_KEY}/" in url or f"/spaces/{SPACE_KEY}/" in url or f"/display/{SPACE_KEY}" in url

def fetch_html(url: str, render_js: bool = False) -> str:
    logger.info("Fetching %s (render_js=%s)", url, render_js)
    if not render_js:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        return r.text
    # if JS required, try Playwright (optional)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        logger.warning("Playwright not available: %s", e)
        r = session.get(url, timeout=30)
        r.raise_for_status()
        return r.text

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        content = page.content()
        browser.close()
        return content

def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Heuristics: Confluence main content often in <div id='main-content'>, 'content' or 'wiki-body'
    selectors = ["#main-content", ".wiki-content", ".content", "#content", ".ak-renderer-document"]
    text = None
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            text = el.get_text("\n", strip=True)
            break
    if not text:
        text = soup.get_text("\n", strip=True)
    # collapse whitespace
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def chunk_text(text: str, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) -> List[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = words[i:i+chunk_size]
        chunks.append(" ".join(chunk))
        if i + chunk_size >= len(words):
            break
        i += chunk_size - overlap
    return chunks

def page_already_indexed(url: str, content_hash: str) -> bool:
    # Query Cognitive Search for docs with url eq '...' and contentHash eq '...'
    # Filter: url eq '...' and contentHash eq '...'
    filter_q = f"url eq '{url.replace(\"'\",\"''\")}' and contentHash eq '{content_hash}'"
    try:
        res = search_client.search(search_text="*", filter=filter_q, top=1)
        for _ in res:
            return True
    except Exception as e:
        logger.debug("Error checking search index for existing doc: %s", e)
    return False

def upload_chunks_to_search(url: str, title: str, chunks: List[str], content_hash: str):
    docs = []
    for i, chunk in enumerate(chunks):
        doc_id = f"{hashlib.sha1((url+str(i)).encode()).hexdigest()}"
        # create embedding
        vec = get_embedding([chunk])[0]
        docs.append({
            "id": doc_id,
            "sourceUrl": url,
            "title": title,
            "content": chunk,
            "chunkIndex": i,
            "contentHash": content_hash,
            "lastScraped": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "embedding": vec
        })
    # upload in batches
    batch_size = 50
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i+batch_size]
        result = search_client.upload_documents(documents=batch)
        logger.info("Uploaded %d docs, result: %s", len(batch), result)

def get_embedding(texts: List[str]) -> List[List[float]]:
    # Calls Azure OpenAI embeddings endpoint for the deployment
    if not AZ_OPENAI_ENDPOINT or not AZ_OPENAI_DEPLOYMENT or not AZ_OPENAI_KEY:
        raise ValueError("Azure OpenAI not configured")
    url = AZ_OPENAI_ENDPOINT.rstrip("/") + f"/openai/deployments/{AZ_OPENAI_DEPLOYMENT}/embeddings?api-version=2024-06-01-preview"
    headers = {"api-key": AZ_OPENAI_KEY, "Content-Type": "application/json"}
    payload = {"input": texts}
    r = requests.post(url, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    j = r.json()
    # response format: data: [{embedding: [..]}, ...]
    return [item["embedding"] for item in j["data"]]

def crawl_space():
    start_url = urljoin(BASE_URL, START_PATH)
    to_visit = [start_url]
    visited = set()
    pages_processed = 0
    while to_visit and pages_processed < SCRAPE_MAX_PAGES:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            html = fetch_html(url, render_js=False)
        except Exception as e:
            logger.warning("Fetch failed for %s, try JS render: %s", url, e)
            try:
                html = fetch_html(url, render_js=True)
            except Exception as ee:
                logger.error("JS render failed for %s: %s", url, ee)
                continue

        # extract text and title
        text = extract_text(html)
        if not text or len(text) < 50:
            logger.info("Skipping short page %s", url)
            continue
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.string if soup.title else url).strip()

        # compute content hash
        content_hash = sha256_hex(text)

        if page_already_indexed(url, content_hash):
            logger.info("No change for %s, skip", url)
        else:
            chunks = chunk_text(text)
            upload_chunks_to_search(url, title, chunks, content_hash)
            logger.info("Indexed %s -> %d chunks", url, len(chunks))

        pages_processed += 1

        # find links
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            parsed = urljoin(BASE_URL, href)
            # normalize: only same host and same space
            if parsed.startswith(BASE_URL) and same_space_url(parsed):
                if parsed not in visited and parsed not in to_visit:
                    to_visit.append(parsed)

    logger.info("Crawl done. visited=%d", len(visited))

if __name__ == "__main__":
    logger.info("Starting ingest worker (space=%s)", SPACE_KEY)
    crawl_space()
