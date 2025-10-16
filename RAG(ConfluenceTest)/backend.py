"""
FastAPI RAG endpoint (backend.py)
Enhanced with strict knowledge base adherence
"""

import os
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv
load_dotenv()

from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential

# env config
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "confluence-vector-index")
EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")

# validate
for name, val in [
    ("AZURE_SEARCH_ENDPOINT", AZURE_SEARCH_ENDPOINT),
    ("AZURE_SEARCH_KEY", AZURE_SEARCH_KEY),
    ("AZURE_OPENAI_ENDPOINT", AZURE_OPENAI_ENDPOINT),
    ("AZURE_OPENAI_KEY", AZURE_OPENAI_KEY),
    ("EMBED_DEPLOYMENT", EMBED_DEPLOYMENT),
    ("CHAT_DEPLOYMENT", CHAT_DEPLOYMENT)
]:
    if not val:
        raise RuntimeError(f"Missing env var {name}")

# Azure OpenAI client
client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2023-05-15",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY)
)

app = FastAPI(title="Confluence RAG API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryReq(BaseModel):
    query: str
    top_k: int = 5

def is_outdated_page(title: str, content: str) -> bool:
    """Check if a page is marked as outdated"""
    outdated_patterns = [
        r'\boutdated\s+version\b',
        r'\barchived\s+version\b',
        r'\blegacy\s+version\b',
        r'\bdeprecated\b',
        r'\bno\s+longer\s+valid\b',
        r'\bold\s+version\b',
        r'\bsuperseded\b',
        r'\bobsolete\b',
        r'\[\s*outdated\s*\]',
        r'\[\s*deprecated\s*\]',
        r'\[\s*archived\s*\]'
    ]
    
    text_to_check = f"{title} {content[:500]}".lower()
    
    for pattern in outdated_patterns:
        if re.search(pattern, text_to_check, re.IGNORECASE):
            return True
    
    return False

def rerank_results(query: str, results: List[dict]) -> List[dict]:
    """Rerank results based on relevance"""
    if len(results) <= 1:
        return results
    
    scored_results = []
    query_lower = query.lower()
    query_terms = set(re.findall(r'\w+', query_lower))
    
    for result in results:
        content = result.get('content', '').lower()
        title = result.get('title', '').lower()
        
        content_terms = set(re.findall(r'\w+', content))
        title_terms = set(re.findall(r'\w+', title))
        
        content_overlap = len(query_terms & content_terms) / max(len(query_terms), 1)
        title_overlap = len(query_terms & title_terms) / max(len(query_terms), 1)
        
        relevance_score = (title_overlap * 2.0) + (content_overlap * 1.0)
        scored_results.append((relevance_score, result))
    
    scored_results.sort(reverse=True, key=lambda x: x[0])
    return [result for _, result in scored_results]

@app.post("/api/query")
def query_endpoint(req: QueryReq):
    q = req.query
    k = min(req.top_k if req.top_k and req.top_k > 0 else 5, 15)  # Increased to 15 for better coverage

    # 1) Embed the query directly (no expansion to keep it focused)
    q_emb = client.embeddings.create(model=EMBED_DEPLOYMENT, input=q).data[0].embedding

    # 2) Vector search with higher k to account for filtering
    search_k = min(k * 3, 45)  # Increased for better recall
    vector_query = VectorizedQuery(vector=q_emb, k_nearest_neighbors=search_k, fields="vector")
    results = search_client.search(
        search_text="",
        vector_queries=[vector_query],
        select=["id", "title", "content", "url", "page_id", "last_modified", "has_video"],
        filter=f"space eq '{SPACE_KEY}'" if SPACE_KEY else None
    )

    # 3) Deduplicate, filter outdated pages
    hits = []
    seen_pages = set()
    filtered_count = 0
    
    for r in results:
        page_id = r.get("page_id")
        title = r.get("title", "")
        content = r.get("content", "")
        
        if page_id in seen_pages:
            continue
            
        if is_outdated_page(title, content):
            filtered_count += 1
            continue
        
        seen_pages.add(page_id)
        hits.append({
            "id": r["id"],
            "title": title,
            "content": content,
            "url": r.get("url", ""),
            "has_video": r.get("has_video", False)
        })

    # 4) Rerank and take top k
    hits = rerank_results(q, hits)[:k]

    # 5) Build prompt with COMPLETE content (not truncated)
    snippets = []
    for i, h in enumerate(hits):
        snippet = h["content"]  # Full content, no truncation
        video_note = " [📹 Video available]" if h.get("has_video") else ""
        
        snippets.append(f"""
=== SOURCE {i+1} ===
Title: {h.get('title')}{video_note}
Content: {snippet}
URL: {h.get('url')}
====================
""")

    # STRICT system prompt - only use provided data
    system_prompt = """You are a Confluence knowledge base assistant. Your ONLY job is to extract and present information that is EXPLICITLY stated in the provided sources.

CRITICAL RULES:
1. ONLY use information that is directly present in the sources below
2. Do NOT make assumptions or add information not in the sources
3. Do NOT provide generic advice or general knowledge
4. If the exact information is in the sources, provide it word-for-word including names, emails, contacts, numbers, dates, steps, etc.
5. If the information is NOT in the sources, say: "I don't have this information in the knowledge base. Please check the Confluence pages directly."
6. ALWAYS extract and include specific details like:
   - Names of people/teams
   - Email addresses
   - Phone numbers
   - Specific steps or procedures
   - Dates and deadlines
   - Links and URLs
   - Any structured data (tables, lists, etc.)

Your response must be a direct extraction from the sources. Do not paraphrase or summarize unless necessary for clarity."""

    user_prompt = f"""Question: {q}

Sources from Confluence Knowledge Base:
{chr(10).join(snippets)}

INSTRUCTIONS:
1. Read through ALL the sources carefully
2. Extract ONLY the information that directly answers the question
3. If you find names, emails, contacts, or specific data - include them EXACTLY as written
4. If the answer requires multiple pieces of information from different sources, combine them
5. If the information is partial, state what you found and what's missing
6. If the information is not in the sources at all, clearly state that

Provide your answer based STRICTLY on the sources above:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # 6) Generate response with strict grounding
    chat_resp = client.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        messages=messages,
        max_tokens=1000,  # Increased for detailed answers
        temperature=0.0,   # Zero temperature for factual accuracy
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0
    )

    assistant_text = chat_resp.choices[0].message.content

    return {
        "answer": assistant_text, 
        "sources": hits,
        "metadata": {
            "filtered_outdated_pages": filtered_count,
            "total_sources_used": len(hits)
        }
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Confluence Knowledge Base API"}
