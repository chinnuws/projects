# backend/app.py
from fastapi import FastAPI, Request
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.projects import AIProjectClient
import os

# MCP Server
CONFLUENCE_BASE_URL=https://your-confluence.yourcompany.com
CONFLUENCE_SPACE_KEY=DOCS
CONFLUENCE_USERNAME=bot-user
CONFLUENCE_PASSWORD=your-pwd

# Azure AI Search
SEARCH_SERVICE=your-ai-search
SEARCH_INDEX=confluence-embeddings
SEARCH_KEY=your-search-key

# Azure AI Foundry
FOUNDRY_ENDPOINT=https://your-foundry.ai.azure.com
FOUNDRY_KEY=your-foundry-key
AGENT_ID=your-agent-id

app = FastAPI()

# Azure AI Search
search_client = SearchClient(
    endpoint=f"https://{os.getenv('SEARCH_SERVICE')}.search.windows.net",
    index_name=os.getenv("SEARCH_INDEX"),
    credential=AzureKeyCredential(os.getenv("SEARCH_KEY"))
)

# Azure AI Foundry
foundry_client = AIProjectClient(
    endpoint=os.getenv("FOUNDRY_ENDPOINT"),
    credential=AzureKeyCredential(os.getenv("FOUNDRY_KEY"))
)

@app.post("/query")
async def handle_query(request: Request):
    data = await request.json()
    query = data["query"]

    # Retrieve from Azure AI Search
    results = search_client.search(
        search_text="",
        vector_queries=[{"k_nearest_neighbors": 3, "fields": "embedding", "vector": get_embedding(query)}],
        select=["content", "title", "url"]
    )
    context = "\n".join([r["content"] for r in results])

    # Generate response using Foundry agent
    response = foundry_client.agents.runs.create(
        agent_id=os.getenv("AGENT_ID"),
        thread_id="temp",
        additional_messages=[{"role": "user", "content": f"Context: {context}\n\nQuestion: {query}"}]
    )
    return {"response": response.output}

def get_embedding(text: str):
    # Use Azure Foundry embedding model
    resp = foundry_client.embeddings.create(input=[text], engine="text-embedding-ada-002")
    return resp['data'][0]['embedding']
