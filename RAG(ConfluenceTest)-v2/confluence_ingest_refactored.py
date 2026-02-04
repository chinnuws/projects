import os
import uuid
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from openai import AzureOpenAI

# ---------------- ENV ----------------
load_dotenv()

CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")  # https://xxx.atlassian.net/wiki
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_SSL_CERT = os.getenv("CONFLUENCE_SSL_CERT")  # optional

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")

# ---------------- CLIENTS ----------------
search_cred = AzureKeyCredential(AZURE_SEARCH_KEY)
index_client = SearchIndexClient(AZURE_SEARCH_ENDPOINT, search_cred)
search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX, search_cred
)

openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2023-05-15",
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

# ---------------- INDEX ----------------
def create_index():
    try:
        index_client.get_index(AZURE_SEARCH_INDEX)
        print("Index already exists")
        return
    except Exception:
        pass

    index_definition = {
        "name": AZURE_SEARCH_INDEX,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True},
            {"name": "page_id", "type": "Edm.String"},
            {"name": "title", "type": "Edm.String", "searchable": True},
            {"name": "content", "type": "Edm.String", "searchable": True},
            {"name": "url", "type": "Edm.String"},
            {
                "name": "content_vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "dimensions": 1536,
                "vectorSearchProfile": "vector-profile",
            },
        ],
        "vectorSearch": {
            "profiles": [
                {"name": "vector-profile", "algorithm": "hnsw-profile"}
            ],
            "algorithms": [
                {
                    "name": "hnsw-profile",
                    "kind": "hnsw",
                    "hnswParameters": {
                        "metric": "cosine",
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500,
                    },
                }
            ],
        },
    }

    index_client.create_index(index_definition)
    print("Index created")

# ---------------- CONFLUENCE ----------------
def fetch_pages():
    pages = []
    start = 0
    limit = 25

    while True:
        url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
        params = {
            "spaceKey": CONFLUENCE_SPACE_KEY,
            "expand": "body.storage,ancestors",
            "limit": limit,
            "start": start,
        }

        resp = requests.get(
            url,
            params=params,
            auth=(CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN),
            verify=CONFLUENCE_SSL_CERT or True,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        pages.extend(data["results"])
        if start + limit >= data["size"]:
            break
        start += limit

    return pages

# ---------------- HTML PARSING ----------------
def parse_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Convert tables to readable text
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if cells:
                rows.append(" | ".join(cells))
        table.replace_with("\n".join(rows))

    return soup.get_text(separator="\n", strip=True)

# ---------------- EMBEDDING ----------------
def embed_text(text: str):
    return openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBED_DEPLOYMENT,
        input=text,
    ).data[0].embedding

# ---------------- INGEST ----------------
def ingest():
    create_index()
    pages = fetch_pages()

    docs = []
    for page in pages:
        title = page["title"]
        page_id = page["id"]
        html = page["body"]["storage"]["value"]
        text = parse_html(html)

        ancestors = page.get("ancestors", [])
        hierarchy = " > ".join(a["title"] for a in ancestors)

        full_text = f"{hierarchy}\n\n{title}\n\n{text}"

        embedding = embed_text(full_text)
        url = f"{CONFLUENCE_BASE_URL}{page['_links']['webui']}"

        docs.append(
            {
                "id": str(uuid.uuid4()),
                "page_id": page_id,
                "title": title,
                "content": full_text,
                "url": url,
                "content_vector": embedding,
            }
        )

        if len(docs) >= 10:
            search_client.upload_documents(docs)
            docs.clear()

    if docs:
        search_client.upload_documents(docs)

    print("Ingestion completed")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    print("Ingestion started")
    ingest()
