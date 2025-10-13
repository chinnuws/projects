import os
import json
import requests
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

load_dotenv()

# Confluence settings
CONFLUENCE_BASE = os.getenv("CONFLUENCE_BASE")
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")

# Azure Search settings
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "confluence-vector-index")

# Azure OpenAI settings
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
EMBED_DEPLOYMENT = os.getenv("EMBED_DEPLOYMENT")

# State file for incremental updates
STATE_FILE = os.getenv("STATE_FILE", "./confluence_ingest_state.json")

# Initialize clients
search_credential = AzureKeyCredential(AZURE_SEARCH_KEY)
index_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=search_credential)
openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2024-02-01",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

def get_embedding(text):
    """Generate embeddings using Azure OpenAI."""
    response = openai_client.embeddings.create(
        input=text,
        model=EMBED_DEPLOYMENT
    )
    return response.data[0].embedding

def create_or_update_index():
    """Create or update the Azure Search index with video metadata fields."""
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SimpleField(name="page_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page_url", type=SearchFieldDataType.String),
        SimpleField(name="space_key", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="version", type=SearchFieldDataType.Int32),
        SimpleField(name="has_video", type=SearchFieldDataType.Boolean, filterable=True),
        SimpleField(name="video_count", type=SearchFieldDataType.Int32),
        SearchableField(name="video_filenames", type=SearchFieldDataType.Collection(SearchFieldDataType.String)),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1536,  # Adjust based on your embedding model
            vector_search_profile_name="myHnswProfile"
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="myHnsw")],
        profiles=[VectorSearchProfile(name="myHnswProfile", algorithm_configuration_name="myHnsw")]
    )

    index = SearchIndex(name=AZURE_SEARCH_INDEX, fields=fields, vector_search=vector_search)
    
    try:
        index_client.create_or_update_index(index)
        print(f"Index '{AZURE_SEARCH_INDEX}' created/updated successfully.")
    except Exception as e:
        print(f"Error creating/updating index: {e}")
        raise

def get_confluence_pages():
    """Fetch all pages from the specified Confluence space."""
    url = f"{CONFLUENCE_BASE}/rest/api/content"
    params = {
        "spaceKey": CONFLUENCE_SPACE_KEY,
        "type": "page",
        "expand": "body.storage,version",
        "limit": 100
    }
    auth = (CONFLUENCE_USER, CONFLUENCE_API_TOKEN)
    
    pages = []
    while url:
        response = requests.get(url, params=params, auth=auth)
        response.raise_for_status()
        data = response.json()
        pages.extend(data.get("results", []))
        url = data.get("_links", {}).get("next")
        if url:
            url = CONFLUENCE_BASE + url
            params = None  # Next URL already contains params
    
    return pages

def get_page_attachments(page_id):
    """Fetch attachments for a specific page and identify videos."""
    url = f"{CONFLUENCE_BASE}/rest/api/content/{page_id}/child/attachment"
    params = {"expand": "version", "limit": 100}
    auth = (CONFLUENCE_USER, CONFLUENCE_API_TOKEN)
    
    response = requests.get(url, params=params, auth=auth)
    response.raise_for_status()
    attachments = response.json().get("results", [])
    
    # Filter video attachments
    video_mimetypes = ["video/mp4", "video/webm", "video/avi", "video/quicktime", 
                       "video/x-msvideo", "video/x-matroska"]
    videos = [att for att in attachments if att.get("metadata", {}).get("mediaType") in video_mimetypes]
    
    return {
        "has_video": len(videos) > 0,
        "video_count": len(videos),
        "video_filenames": [v.get("title") for v in videos]
    }

def load_state():
    """Load the ingestion state from file."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    """Save the ingestion state to file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def ingest_pages():
    """Ingest pages from Confluence into Azure Search."""
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX,
        credential=search_credential
    )
    
    state = load_state()
    pages = get_confluence_pages()
    current_page_ids = set()
    
    for page in pages:
        page_id = page["id"]
        current_page_ids.add(page_id)
        version = page["version"]["number"]
        title = page["title"]
        content = page.get("body", {}).get("storage", {}).get("value", "")
        
        # Check if page needs updating
        if page_id in state and state[page_id]["version"] >= version:
            print(f"Skipping '{title}' (no changes)")
            continue
        
        # Get video attachment information
        video_info = get_page_attachments(page_id)
        
        # Construct page URL
        page_url = f"{CONFLUENCE_BASE}/pages/viewpage.action?pageId={page_id}"
        
        # Generate embedding
        text_to_embed = f"{title}\n{content}"
        embedding = get_embedding(text_to_embed)
        
        # Prepare document
        document = {
            "id": page_id,
            "content": content,
            "title": title,
            "page_id": page_id,
            "page_url": page_url,
            "space_key": CONFLUENCE_SPACE_KEY,
            "version": version,
            "has_video": video_info["has_video"],
            "video_count": video_info["video_count"],
            "video_filenames": video_info["video_filenames"],
            "content_vector": embedding
        }
        
        # Upload to Azure Search
        search_client.upload_documents(documents=[document])
        print(f"Indexed '{title}' (version {version}){' [HAS VIDEO]' if video_info['has_video'] else ''}")
        
        # Update state
        state[page_id] = {"version": version, "title": title}
    
    # Delete pages that no longer exist
    deleted_pages = set(state.keys()) - current_page_ids
    for page_id in deleted_pages:
        search_client.delete_documents(documents=[{"id": page_id}])
        print(f"Deleted page '{state[page_id]['title']}'")
        del state[page_id]
    
    save_state(state)
    print("Ingestion complete!")

if __name__ == "__main__":
    create_or_update_index()
    ingest_pages()
