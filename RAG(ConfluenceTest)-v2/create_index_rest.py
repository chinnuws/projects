import os
import requests
from dotenv import load_dotenv

load_dotenv()

endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
key = os.getenv("AZURE_SEARCH_KEY")
index_name = os.getenv("AZURE_SEARCH_INDEX")

url = f"{endpoint}/indexes/{index_name}?api-version=2023-11-01"
headers = {
    "Content-Type": "application/json",
    "api-key": key
}

# Check if index exists
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    print("ℹ️ Index already exists. Skipping creation.")
    exit(0)

index_payload = {
    "name": index_name,
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True},
        {"name": "title", "type": "Edm.String", "searchable": True},
        {"name": "content", "type": "Edm.String", "searchable": True},
        {
            "name": "content_vector",
            "type": "Collection(Edm.Single)",
            "searchable": True,
            "dimensions": 1536,
            "vectorSearchConfiguration": "default"
        },
        {"name": "url", "type": "Edm.String", "filterable": True},
        {"name": "space", "type": "Edm.String", "filterable": True},
        {"name": "parent_id", "type": "Edm.String", "filterable": True}
    ],
    "vectorSearch": {
        "algorithmConfigurations": [
            {
                "name": "default",
                "kind": "hnsw",
                "hnswParameters": {
                    "metric": "cosine",
                    "m": 4,
                    "efConstruction": 400,
                    "efSearch": 500
                }
            }
        ]
    }
}

resp = requests.put(url, headers=headers, json=index_payload)
resp.raise_for_status()
print("✅ Index created successfully")
