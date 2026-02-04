import os
import uuid
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchableField,
    SimpleField
)
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from openai import AzureOpenAI

# ======================
# ENV
# ======================
load_dotenv()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX")

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")
CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = "2023-05-15"

CHUNK_MAX_CHARS = 3000
CHUNK_OVERLAP_CHARS = 400
EMBEDDING_DIMENSION = 1536
BATCH_SIZE = 16

# ======================
# CLIENTS
# ======================
openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

index_client = SearchIndexClient(
    AZURE_SEARCH_ENDPOINT,
    AzureKeyCredential(AZURE_SEARCH_KEY)
)

search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    INDEX_NAME,
    AzureKeyCredential(AZURE_SEARCH_KEY)
)

# ======================
# INDEX
# ======================
def index_exists():
    try:
        index_client.get_index(INDEX_NAME)
        print(f"ℹ️ Index '{INDEX_NAME}' already exists")
        return True
    except ResourceNotFoundError:
        return False


def create_index():
    if index_exists():
        return

    print("🆕 Creating index")

    index = SearchIndex(
        name=INDEX_NAME,
        fields=[
            SimpleField(name="id", type="Edm.String", key=True),
            SearchableField(name="title", type="Edm.String"),
            SearchableField(name="content", type="Edm.String"),
            SimpleField(
                name="content_vector",
                type="Collection(Edm.Single)",
                searchable=True,
                vector_search_dimensions=EMBEDDING_DIMENSION
            ),
            SimpleField(name="url", type="Edm.String", filterable=True),
            SimpleField(name="space", type="Edm.String", filterable=True),
            SimpleField(name="parent_id", type="Edm.String", filterable=True),
        ]
    )

    index_client.create_index(index)
    print("✅ Index created")

# ======================
# CONFLUENCE FETCH
# ======================
def fetch_pages():
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    params = {
        "spaceKey": CONFLUENCE_SPACE_KEY,
        "expand": "body.storage,ancestors",
        "limit": 50
    }

    headers = {"Authorization": f"Bearer {CONFLUENCE_TOKEN}"}
    pages = []

    while url:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data["results"])
        url = data["_links"].get("next")
        if url:
            url = CONFLUENCE_BASE_URL + url

    return pages

# ======================
# HTML → TEXT (TABLE SAFE)
# ======================
def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Convert tables to markdown
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        md = "\n\n| " + " | ".join(
            th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])
        ) + " |\n"

        md += "| " + " | ".join("---" for _ in rows[0].find_all(["th", "td"])) + " |\n"

        for row in rows[1:]:
            md += "| " + " | ".join(
                cell.get_text(strip=True) for cell in row.find_all(["td", "th"])
            ) + " |\n"

        table.replace_with(md)

    return soup.get_text(separator="\n")

# ======================
# CHUNKING
# ======================
def chunk_text(text):
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_MAX_CHARS
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP_CHARS
    return chunks

# ======================
# EMBEDDINGS
# ======================
def embed(texts):
    response = openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=texts
    )
    return [d.embedding for d in response.data]

# ======================
# INGEST
# ======================
def ingest():
    print("🚀 Ingestion started")
    create_index()

    pages = fetch_pages()
    docs = []

    for page in pages:
        ancestors = page.get("ancestors", [])
        parent_id = ancestors[-1]["id"] if ancestors else None
        parent_titles = " > ".join(a["title"] for a in ancestors)

        raw_html = page["body"]["storage"]["value"]
        clean_text = html_to_markdown(raw_html)

        # 🔑 Parent context injected here
        contextual_text = f"""
Page Title: {page['title']}
Parent Path: {parent_titles}

{clean_text}
"""

        chunks = chunk_text(contextual_text)

        for chunk in chunks:
            docs.append({
                "id": str(uuid.uuid4()),
                "title": page["title"],
                "content": chunk,
                "url": f"{CONFLUENCE_BASE_URL}{page['_links']['webui']}",
                "space": CONFLUENCE_SPACE_KEY,
                "parent_id": parent_id
            })

    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        vectors = embed([d["content"] for d in batch])

        for d, v in zip(batch, vectors):
            d["content_vector"] = v

        search_client.upload_documents(batch)
        print(f"⬆️ Uploaded {i + len(batch)} docs")

    print("🎉 Ingestion complete")


if __name__ == "__main__":
    ingest()
