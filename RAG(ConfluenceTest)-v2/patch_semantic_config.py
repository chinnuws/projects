import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_KEY = os.environ["AZURE_SEARCH_KEY"]
INDEX_NAME = os.environ["AZURE_SEARCH_INDEX"]

url = f"{SEARCH_ENDPOINT}/indexes/{INDEX_NAME}?api-version=2023-11-01"
headers = {
    "Content-Type": "application/json",
    "api-key": SEARCH_KEY
}

# 1. Get existing index definition
print("📥 Fetching current index definition...")
resp = requests.get(url, headers=headers)
resp.raise_for_status()
index_def = resp.json()

# 2. Inject semantic configuration
print("🔧 Adding semantic configuration...")
index_def["semantic"] = {
    "configurations": [
        {
            "name": "default",
            "prioritizedFields": {
                "titleField": {
                    "fieldName": "title"
                },
                "contentFields": [
                    {"fieldName": "content"}
                ]
            }
        }
    ]
}

# 3. Update index
print("📤 Updating index...")
update_resp = requests.put(url, headers=headers, json=index_def)
update_resp.raise_for_status()

print("✅ Semantic configuration added successfully")
