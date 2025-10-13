import os
from typing import List, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

load_dotenv()

app = FastAPI(title="Confluence RAG API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Azure Search settings
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "confluence-vector-index")

# Azure OpenAI settings
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
EMBED_DEPLOYMENT = os.getenv("EMBED_DEPLOYMENT")
CHAT_DEPLOYMENT = os.getenv("CHAT_DEPLOYMENT")

# Initialize clients
search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY)
)

openai_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2024-02-01",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class SourceDocument(BaseModel):
    page_title: str
    page_url: str
    has_video: bool
    video_count: int
    video_filenames: List[str]
    relevance_score: float
    content_snippet: str


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceDocument]


def get_embedding(text: str) -> List[float]:
    """Generate embeddings using Azure OpenAI."""
    response = openai_client.embeddings.create(
        input=text,
        model=EMBED_DEPLOYMENT
    )
    return response.data[0].embedding


@app.post("/api/query", response_model=QueryResponse)
async def query_confluence(request: QueryRequest):
    """Query the Confluence knowledge base and return answer with sources."""
    try:
        # Generate query embedding
        query_vector = get_embedding(request.query)
        
        # Search Azure AI Search
        results = search_client.search(
            search_text=request.query,
            vector_queries=[{
                "vector": query_vector,
                "k_nearest_neighbors": request.top_k,
                "fields": "content_vector"
            }],
            select=["title", "content", "page_url", "has_video", "video_count", "video_filenames"],
            top=request.top_k
        )
        
        # Collect context and source documents
        context_parts = []
        sources = []
        
        for result in results:
            score = result.get("@search.score", 0.0)
            content = result.get("content", "")
            
            # Add to context for RAG
            context_parts.append(f"**{result['title']}**\n{content}")
            
            # Add to sources
            sources.append(SourceDocument(
                page_title=result.get("title", "Untitled"),
                page_url=result.get("page_url", ""),
                has_video=result.get("has_video", False),
                video_count=result.get("video_count", 0),
                video_filenames=result.get("video_filenames", []),
                relevance_score=round(score, 4),
                content_snippet=content[:200] + "..." if len(content) > 200 else content
            ))
        
        if not context_parts:
            return QueryResponse(
                answer="I couldn't find relevant information to answer your question.",
                sources=[]
            )
        
        # Generate answer using Azure OpenAI
        context = "\n\n".join(context_parts)
        messages = [
            {"role": "system", "content": "You are a helpful assistant that answers questions based on the provided Confluence documentation. Always cite the source when answering."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {request.query}\n\nAnswer:"}
        ]
        
        response = openai_client.chat.completions.create(
            model=CHAT_DEPLOYMENT,
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        answer = response.choices[0].message.content
        
        return QueryResponse(answer=answer, sources=sources)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
