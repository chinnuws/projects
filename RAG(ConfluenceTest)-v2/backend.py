"""
backend.py
FastAPI backend for Confluence RAG
- Azure AI Search (vector + semantic reranker)
- Azure OpenAI chat + embeddings
- Compatible with azure-search-documents 11.6.x
"""

import os
import logging
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Azure Search
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

# Azure OpenAI
from openai import AzureOpenAI

# --------------------------------------------------
# ENV
# --------------------------------------------------
load_dotenv()
logging.basicConfig(level=logging.INFO)

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
TOP_K = int(os.getenv("TOP_K", "10"))  # Increased to get more results for deduplication

# --------------------------------------------------
# CLIENTS
# --------------------------------------------------
search_client = SearchClient(
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_INDEX,
    AzureKeyCredential(AZURE_SEARCH_KEY),
)

aoai = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version="2023-05-15",
)

# --------------------------------------------------
# FASTAPI
# --------------------------------------------------
app = FastAPI(title="Confluence RAG API")

# Add CORS middleware for Kubernetes deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    sources: List[dict]

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def embed_query(text: str) -> List[float]:
    """Generate embedding for query text"""
    resp = aoai.embeddings.create(
        model=EMBED_DEPLOYMENT,
        input=text,
    )
    return resp.data[0].embedding

def retrieve(query: str):
    """
    Retrieve relevant documents using hybrid search (vector + semantic)
    Returns top 6 unique Confluence pages
    """
    query_vector = embed_query(query)
    
    results = search_client.search(
        search_text=query,  # lexical + semantic
        vector_queries=[{
            "kind": "vector",  # REQUIRED for 11.6.x+
            "vector": query_vector,
            "fields": "content_vector",  # FIXED: Changed from "vector" to "content_vector"
            "k": TOP_K,
        }],
        query_type="semantic",
        semantic_configuration_name="default",
        top=TOP_K,
    )
    
    # ADDED: Deduplicate by page_id to get unique pages (top 6)
    seen_pages = {}
    all_chunks = []  # Keep all chunks for answer generation
    
    for r in results:
        page_id = r.get("page_id")
        title = r.get("title", "Untitled")
        content = r.get("content", "")
        url = r.get("url", "")
        score = r.get("@search.score", 0)
        
        # Collect all chunks for context
        all_chunks.append({
            "title": title,
            "content": content,
            "url": url,
            "score": score,
            "page_id": page_id,
        })
        
        # Track unique pages for sources (limit to top 6)
        if page_id and page_id not in seen_pages and len(seen_pages) < 6:
            seen_pages[page_id] = {
                "title": title,
                "url": url,
                "score": score,
                "page_id": page_id,
            }
    
    return all_chunks, list(seen_pages.values())

def generate_answer(query: str, docs: List[dict]) -> str:
    """Generate answer using Azure OpenAI with retrieved context"""
    if not docs:
        return "I could not find relevant information in Confluence."
    
    # Use top relevant chunks for context
    context = "\n\n".join(
        f"Title: {d['title']}\nContent: {d['content']}"
        for d in docs[:5]  # Use top 5 chunks for context
    )
    
    system_prompt = (
        "You are an internal knowledge assistant.\n"
        "Answer ONLY using the provided Confluence content.\n"
        "If the answer is not present, say you do not know.\n"
        "Be concise and accurate."
    )
    
    resp = aoai.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Question: {query}\n\nConfluence Content:\n{context}",
            },
        ],
    )
    
    return resp.choices[0].message.content.strip()

# --------------------------------------------------
# API ENDPOINTS
# --------------------------------------------------
@app.post("/query", response_model=QueryResponse)
def query_rag(req: QueryRequest):
    """
    Main RAG endpoint
    - Retrieves relevant documents from Azure AI Search
    - Generates answer using Azure OpenAI
    - Returns answer with top 6 unique source pages
    """
    try:
        # Retrieve documents (all chunks + unique pages)
        all_chunks, unique_pages = retrieve(req.query)
        
        # Generate answer using all relevant chunks
        answer = generate_answer(req.query, all_chunks)
        
        # Return unique pages as sources (top 6)
        return QueryResponse(answer=answer, sources=unique_pages)
    
    except Exception as e:
        logging.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "ok"}

# --------------------------------------------------
# Additional endpoints for debugging
# --------------------------------------------------
@app.get("/")
def root():
    """Root endpoint"""
    return {
        "service": "Confluence RAG API",
        "status": "running",
        "endpoints": {
            "query": "/query",
            "health": "/health",
        }
    }
