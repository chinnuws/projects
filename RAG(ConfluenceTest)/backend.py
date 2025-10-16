"""
FastAPI RAG endpoint (backend.py)
Enhanced with intelligent query processing and contextual understanding
Filters out outdated pages from results
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
    """
    Check if a page is marked as outdated based on title or content.
    Returns True if the page should be filtered out.
    """
    # Patterns that indicate outdated content
    outdated_patterns = [
        r'\boutdated\s+version\b',
        r'\boldated\s+version\b',
        r'\barchived\s+version\b',
        r'\blegacy\s+version\b',
        r'\bdeprecated\b',
        r'\bno\s+longer\s+valid\b',
        r'\bno\s+longer\s+current\b',
        r'\bold\s+version\b',
        r'\bsuperseded\b',
        r'\bobsolete\b',
        r'\[\s*outdated\s*\]',
        r'\[\s*deprecated\s*\]',
        r'\[\s*archived\s*\]'
    ]
    
    # Check title and content (case-insensitive)
    text_to_check = f"{title} {content[:500]}".lower()
    
    for pattern in outdated_patterns:
        if re.search(pattern, text_to_check, re.IGNORECASE):
            return True
    
    return False

def expand_query(query: str) -> str:
    """
    Expand the query with contextual understanding to improve search results.
    This helps handle various phrasings and informal language.
    """
    # Use LLM to expand/rephrase query for better semantic understanding
    expansion_prompt = f"""Given this user question, generate an expanded version that captures the semantic meaning and intent, including related terms and concepts. Keep it concise.

Original question: {query}

Expanded question (one sentence):"""
    
    try:
        expansion_response = client.chat.completions.create(
            model=CHAT_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a query expansion assistant. Expand user queries to capture semantic meaning while staying concise."},
                {"role": "user", "content": expansion_prompt}
            ],
            max_tokens=100,
            temperature=0.3
        )
        expanded = expansion_response.choices[0].message.content.strip()
        # Combine original and expanded for better coverage
        return f"{query} {expanded}"
    except:
        return query

def rerank_results(query: str, results: List[dict]) -> List[dict]:
    """
    Rerank results based on relevance to the query using semantic understanding.
    """
    if len(results) <= 1:
        return results
    
    # Simple relevance scoring based on content overlap
    scored_results = []
    query_lower = query.lower()
    query_terms = set(re.findall(r'\w+', query_lower))
    
    for result in results:
        content = result.get('content', '').lower()
        title = result.get('title', '').lower()
        
        # Calculate relevance score
        content_terms = set(re.findall(r'\w+', content))
        title_terms = set(re.findall(r'\w+', title))
        
        # Term overlap scoring
        content_overlap = len(query_terms & content_terms) / max(len(query_terms), 1)
        title_overlap = len(query_terms & title_terms) / max(len(query_terms), 1)
        
        # Title matches are more important
        relevance_score = (title_overlap * 2.0) + (content_overlap * 1.0)
        
        scored_results.append((relevance_score, result))
    
    # Sort by relevance score
    scored_results.sort(reverse=True, key=lambda x: x[0])
    
    return [result for _, result in scored_results]

@app.post("/api/query")
def query_endpoint(req: QueryReq):
    q = req.query
    k = min(req.top_k if req.top_k and req.top_k > 0 else 5, 10)  # Cap at 10

    # 1) Expand query for better semantic understanding
    expanded_query = expand_query(q)
    
    # 2) Embed the expanded query
    q_emb = client.embeddings.create(model=EMBED_DEPLOYMENT, input=expanded_query).data[0].embedding

    # 3) Vector search with higher k to allow for filtering and reranking
    search_k = min(k * 3, 30)  # Get more results to account for filtering outdated pages
    vector_query = VectorizedQuery(vector=q_emb, k_nearest_neighbors=search_k, fields="vector")
    results = search_client.search(
        search_text="",
        vector_queries=[vector_query],
        select=["id", "title", "content", "url", "page_id", "last_modified", "has_video"],
        filter=f"space eq '{SPACE_KEY}'" if SPACE_KEY else None
    )

    # 4) Deduplicate by page_id, filter outdated pages, and collect results
    hits = []
    seen_pages = set()
    filtered_count = 0
    
    for r in results:
        page_id = r.get("page_id")
        title = r.get("title", "")
        content = r.get("content", "")
        
        # Skip if already seen
        if page_id in seen_pages:
            continue
            
        # Filter out outdated pages
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

    # 5) Rerank results based on relevance
    hits = rerank_results(q, hits)[:k]  # Take top k after reranking

    # 6) Build enhanced prompt with better context understanding
    snippets = []
    for i, h in enumerate(hits):
        snippet = h["content"]
        if len(snippet) > 1200:
            snippet = snippet[:1200] + "..."
        
        video_note = " [📹 Contains video content]" if h.get("has_video") else ""
        snippets.append(f"""
Source {i+1}: {h.get('title')}{video_note}
Content: {snippet}
URL: {h.get('url')}
""")

    # Enhanced system prompt for better understanding
    system_prompt = """You are an intelligent Confluence knowledge assistant with expertise in understanding context and user intent.

Your capabilities:
- Understand questions regardless of phrasing (casual, formal, technical, or incomplete)
- Extract the core intent and context from user queries
- Provide accurate, precise answers based on the provided sources
- Synthesize information from multiple sources when relevant
- Recognize when information is incomplete or unavailable
- Only reference current, up-to-date information (outdated content has been filtered out)

Guidelines:
- If the answer is in the sources, provide it clearly and concisely
- If sources contain partial information, synthesize a helpful response and mention what's available
- If the answer isn't in the sources, acknowledge this clearly and suggest what might help
- When video content is available, mention it as an additional resource
- Use natural, conversational language while being professional
- Focus on the user's actual need, not just the literal question"""

    user_prompt = f"""User Question: {q}

Available Sources (current and up-to-date):
{chr(10).join(snippets)}

Instructions:
1. Understand the core intent of the user's question (even if phrased informally or incompletely)
2. Find the most relevant information in the sources above
3. Provide a precise, accurate answer that directly addresses the user's need
4. If sources contain video content, mention it as additional reference
5. If information is partial or missing, be transparent about it

Answer:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # 7) Generate intelligent response
    chat_resp = client.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        messages=messages,
        max_tokens=800,  # Increased for more comprehensive answers
        temperature=0.2,  # Slight temperature for more natural responses
        top_p=0.95,
        frequency_penalty=0.3,  # Reduce repetition
        presence_penalty=0.3   # Encourage diverse language
    )

    assistant_text = chat_resp.choices[0].message.content

    return {
        "answer": assistant_text, 
        "sources": hits,
        "metadata": {
            "filtered_outdated_pages": filtered_count
        }
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Confluence Knowledge Base API"}
