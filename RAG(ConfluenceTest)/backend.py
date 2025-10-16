"""
FastAPI RAG endpoint (backend.py)
Strictly grounded responses - only from knowledge base content
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
    
    text_to_check = f"{title} {content[:500]}".lower()
    
    for pattern in outdated_patterns:
        if re.search(pattern, text_to_check, re.IGNORECASE):
            return True
    
    return False

def rerank_results(query: str, results: List[dict]) -> List[dict]:
    """
    Rerank results based on relevance to the query.
    """
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
    k = min(req.top_k if req.top_k and req.top_k > 0 else 5, 10)

    # 1) Embed the query (no expansion - more precise grounding)
    q_emb = client.embeddings.create(model=EMBED_DEPLOYMENT, input=q).data[0].embedding

    # 2) Vector search
    search_k = min(k * 2, 20)
    vector_query = VectorizedQuery(vector=q_emb, k_nearest_neighbors=search_k, fields="vector")
    results = search_client.search(
        search_text="",
        vector_queries=[vector_query],
        select=["id", "title", "content", "url", "page_id", "last_modified", "has_video"],
        filter=f"space eq '{SPACE_KEY}'" if SPACE_KEY else None
    )

    # 3) Deduplicate and filter
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

    # 4) Rerank
    hits = rerank_results(q, hits)[:k]

    # 5) Build strict grounded prompt
    snippets = []
    for i, h in enumerate(hits):
        snippet = h["content"]
        if len(snippet) > 1500:
            snippet = snippet[:1500] + "..."
        
        video_note = " [Contains Video]" if h.get("has_video") else ""
        snippets.append(f"""
===== SOURCE {i+1} =====
Title: {h.get('title')}{video_note}
Content: {snippet}
URL: {h.get('url')}
""")

    # STRICT system prompt - no external knowledge
    system_prompt = """You are a Confluence documentation assistant. You must ONLY provide information that is explicitly stated in the sources below.

STRICT RULES:
1. ONLY use information directly found in the provided sources
2. Do NOT add any external knowledge, assumptions, or generalizations
3. Do NOT make up information or provide generic advice
4. If the exact answer is not in the sources, clearly state: "I don't have this information in the available documentation."
5. Quote or paraphrase directly from the sources
6. When referencing information, be specific about which source it came from
7. If sources mention video content, inform the user they can watch the video for details

Your response must be a direct answer based solely on the source content."""

    # Check if we have relevant sources
    if not hits:
        return {
            "answer": "I don't have any relevant information in the knowledge base to answer this question. Please check the Confluence documentation directly or rephrase your question.",
            "sources": [],
            "metadata": {"filtered_outdated_pages": filtered_count}
        }

    user_prompt = f"""Question: {q}

Available Sources from Knowledge Base:
{chr(10).join(snippets)}

INSTRUCTIONS:
- Answer ONLY using the information in the sources above
- Do NOT add any information from outside the sources
- If the answer is not in the sources, say so clearly
- Be precise and specific - quote or paraphrase from the sources
- If a source has video content, mention it

Answer based strictly on the sources:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # 6) Generate grounded response
    chat_resp = client.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        messages=messages,
        max_tokens=600,
        temperature=0.0,  # Zero temperature for strict grounding
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0
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
