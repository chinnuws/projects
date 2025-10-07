Install Streamlit:
pip install streamlit requests

1. Set up Python virtual environment (optional but recommended)
python -m venv oaisearchpoc
source oaisearchpoc/Scripts/activate

2. Install backend dependencies from requirements.txt
pip install -r backend/requirements.txt

3. Run the backend FastAPI app (app.py)
From the backend/ directory (or wherever your app.py is located):
uvicorn app:app --reload
This starts the backend API server at http://localhost:8000.
The Streamlit frontend will call it when sending chat queries.

Run the frontend app:
streamlit run app_frontend.py

4. (One-time or as needed) Run the embedding & indexing script
To upload your hardcoded facts embeddings to Azure Cognitive Search (typically run once or anytime knowledge base changes):
python backend/embed_and_index.py


-------------------------------------------------------------------------------------------------------------------

1. Azure Cognitive Search Service (Azure AI Search)
Purpose:
Stores and indexes your knowledge base documents and their vector embeddings. Enables semantic and vector search retrieval to find relevant content based on user queries.

Setup Steps:

Navigate to Azure Portal > Create a Resource > Search > Azure AI Search
Create a Search service instance:
Choose Subscription and Resource Group
Specify a globally unique name for the Search service
Select Pricing Tier (choose at least S1 or above to enable vector capabilities)
Select Region close to your user base
After deployment, go to Keys blade to get:
Admin API Key (used to create and upload indexes)
Query Key (used for searching, less privileged)

2. Azure OpenAI Service
Purpose:
Hosts OpenAI models such as GPT-35-turbo and embedding models to generate embeddings and generate answers.

Setup Steps:
Navigate to Azure Portal > Create a Resource > AI + Machine Learning > Azure OpenAI

Create Azure OpenAI resource:
Choose Subscription and Resource Group
Provide Resource Name
Choose Supported Region
After deployment, locate the endpoint URL and generate an API Key

Deploy Model(s):
Under the Azure OpenAI resource, create deployments for the models you need:
GPT-35-turbo (or GPT-4 for completions)
Text-embedding-ada-002 (or equivalent) for embeddings

3. Azure App Service (Optional but Recommended for Deployment)
Purpose:
Host the backend API (app.py) and frontend React app if you want to deploy the chatbot to the cloud for easy access.

Setup Steps:
Navigate to Azure Portal > Create a Resource > Web > App Service
Select Subscription and Resource Group
Provide a unique App Service name
Choose Runtime Stack (e.g., Python 3.x if backend in Python)
Select Region matching your other services
After deployment, configure Deployment Center or use GitHub Actions/CLI to deploy your app

4. (Optional) Azure Storage Account
Purpose:
If you plan to enable file uploads from frontend and store them temporarily for ingestion or further processing, 
use Azure Blob Storage.

Setup Steps:
Navigate to Azure Portal > Create a Resource > Storage > Storage Account
Choose Subscription, Resource Group, and Storage Account Name
Choose Performance and Access Tier
Create container(s) for storing uploaded files

---------------------------------------------------------------------------------------------------------
1. Set up Python environment
python -m venv oaisearchpoc
source oaisearchpoc/Scripts/activate

2. Install dependencies
pip install -r requirements.txt
pip install streamlit requests

3. Run the backend (FastAPI app)
uvicorn embed_and_index:app --reload --port 8000
This starts the backend API server at http://localhost:8000

4. Run the frontend (Streamlit app)
streamlit run app_frontend.py

5. Run the embedding and indexing script (for initializing document vectors)
python embed_and_index.py

---------------------------------------------------------------------------------------------------------

Service	Purpose	            Key Configurations
Azure AI Search	            Index and vector search of documents	Pricing tier S1+, Admin & Query keys
Azure OpenAI	            Hosting GPT and embedding models	    Endpoint URL, API key, Deploy models
Azure App Service (opt.)	Host backend and frontend apps	        Runtime (Python/Node), Deployment option
Azure Storage (opt.)	    Store uploaded files from frontend	    Blob containers for file storage

-------------------------------------------------------------------------------------------------------

uvicorn embed_and_index:app --reload --port 8000
streamlit run app_frontend.py

python -m pip install --upgrade --force-reinstall --no-cache-dir azure-search-documents==11.6.0b11
python -m pip show azure-search-documents
