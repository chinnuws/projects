1. Install backend dependencies from requirements.txt
pip install -r requirements.txt

2. Start MCP scraper:
confluence-scraper-mcp --web

3. Start FastAPI backend:
uvicorn backend/app:app --reload

4. Start Streamlit frontend:
streamlit run app.py

Open http://localhost:8501 to access the chatbot.


# Confluence AI Chatbot with Azure AI Foundry, Azure AI Search, and Streamlit

This repository contains a full-stack Retrieval-Augmented Generation (RAG) chatbot that enables users to query internal Confluence documentation using natural language. The solution integrates `confluence-scraper-mcp`, Azure AI Search, Azure AI Foundry, and a Streamlit frontend.

## 🌐 Complete System Flow

### 1. Data Extraction via confluence-scraper-mcp

The `confluence-scraper-mcp` server runs locally and scrapes Confluence pages without requiring an API key. It uses HTTP requests (and optional authentication) to access Confluence content within the internal network. Pages are parsed from HTML to plain text, chunked, and made available via an MCP endpoint (`http://localhost:8000/crawl`). This server acts as a **Model Context Protocol (MCP)** service, exposing structured Confluence data to AI agents[web:7][web:91][web:92].

### 2. Embedding Generation and Indexing in Azure AI Search

A script or backend service calls the MCP server to fetch all Confluence pages. Each text chunk is sent to **Azure AI Foundry** (or Azure OpenAI) to generate embeddings using a model like `text-embedding-ada-002`. These embeddings, along with the original text and metadata (title, URL), are uploaded to **Azure AI Search**. A vector-enabled index is created to support semantic search, enabling fast retrieval of relevant content based on user queries[web:63][web:106][web:108].

### 3. Agent Setup in Azure AI Foundry

An **AI agent** is created in Azure AI Foundry with:
- A large language model (e.g., `gpt-4o`)
- Instructions: _"Answer user questions using Confluence data via MCP and Azure AI Search."_
- Tools: MCP server and Azure AI Search connector

The agent is assigned a unique **AGENT_ID**, used to invoke it programmatically[web:59][web:60][web:107].

### 4. User Query via Streamlit Chatbot

The **Streamlit frontend** provides a chat interface where users ask questions about Confluence content. When a user submits a query:
- The message is sent to the **FastAPI backend** (`http://localhost:8001/query`)
- The backend:
  1. **Searches Azure AI Search** using vector similarity to find the most relevant Confluence content
  2. **Retrieves context** (e.g., project timelines, policies)
  3. **Invokes the Azure AI Foundry agent** using the `AGENT_ID`, passing the context and user query
  4. **Receives a generated response** grounded in Confluence data
- The response is sent back to the Streamlit UI and displayed to the user[web:73][web:78][web:96]





