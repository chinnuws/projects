Instructions:

1) Create virtualenv and install requirements:
python -m venv confluencepoc
source confluencepoc/Scripts/activate

python -m pip install --upgrade --force-reinstall --no-cache-dir azure-search-documents==11.6.0b11
python -m pip show azure-search-documents

pip install --upgrade pip
pip install -r requirements.txt

2) Create .env file
Edit .env and fill in:
Confluence: CONFLUENCE_BASE, CONFLUENCE_USER, CONFLUENCE_API_TOKEN, CONFLUENCE_SPACE_KEY
Azure Search: AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY
Azure OpenAI: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, EMBED_DEPLOYMENT, CHAT_DEPLOYMENT
Ensure AZURE_SEARCH_INDEX is set or leave default 'confluence-vector-index'

3) Run the ingest once (this creates index if missing and ingests)
From project root:
python ingest_and_index.py

Notes:
This will create/overwrite local STATE_FILE (default ./confluence_ingest_state.json).
If you change embedding deployment/model later, you may need to recreate the index.

4) Run the FastAPI RAG API

start uvicorn:
uvicorn backend:app --reload --host 0.0.0.0 --port 8000

The API is available at http://127.0.0.1:8000
Test with:
curl -X POST "http://127.0.0.1:8000/api/query" -H "Content-Type: application/json" -d '{"query":"How to set up X?","top_k":5}'

5) Run the Streamlit frontend
streamlit run frontend_streamlit.py

The Streamlit UI will open in your browser (default http://localhost:8501).
If your API is not on localhost:8000, set env API_URL to point to your API (e.g., http://api-host:8000)

6) Re-running ingest (incremental updates)
After the initial run, just re-run the ingest script:
python ingest_and_index.py

The script will:
check if index exists (creates if missing)
list pages in the hard-coded space
compare page versions with local state
fetch & reindex changed pages only, and delete pages removed from the space.

7) Troubleshooting & tips
-------------------------
If you change embedding model/deployment with a different vector dimension:
You must recreate the search index (delete & allow the ingest script to re-create).
Keep secrets in a secure store for production (Azure Key Vault, Managed Identity).
For production, use a small DB (Cosmos/Postgres) instead of the local state JSON file.
Add retries/backoffs for network/API errors in production.








