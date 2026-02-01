```
CHUNK_MAX_CHARS=1800
CHUNK_OVERLAP_CHARS=200
BATCH_SIZE=16
```

# 🚀 Production-Grade RAG Improvements  
**Azure AI Search + Confluence Knowledge Base**

This guide outlines the key improvements needed to upgrade your Retrieval-Augmented Generation (RAG) system to production-grade quality using **Azure AI Search** and **Confluence** as a source.

---

## ✅ What’s Already Working Well

### Ingestion
- Incremental ingest with version tracking  
- Vector embeddings stored correctly  
- Page-level metadata (labels, space, URL, last_modified)  
- Deleted page detection and index cleanup  

### Backend
- Temperature set to 0  
- Vector topK expansion (`k * 3`)  
- Deduplication by `page_id`  
- Filtering outdated content  
- Guardrail: *Answer only from sources*  

**Your foundation is solid — improvements focus on structure and retrieval quality.**

---

# 1️⃣ Ingestion Issues (Biggest Impact Area)

## ❌ Problem 1: HTML Stripping Removes Structure

Naive tag removal destroys document meaning.

```python
def convert_storage_to_text(storage_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", storage_html)
```

### 🔥 Fix: Preserve Headings, Lists, and Tables

```python
def convert_storage_to_text(storage_html: str) -> str:
    storage_html = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n\n# \1\n\n", storage_html)
    storage_html = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n\n## \1\n\n", storage_html)
    storage_html = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n\n### \1\n\n", storage_html)

    storage_html = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", storage_html)

    storage_html = re.sub(r"<tr[^>]*>(.*?)</tr>", r"\n\1", storage_html)
    storage_html = re.sub(r"<th[^>]*>(.*?)</th>", r" \1 |", storage_html)
    storage_html = re.sub(r"<td[^>]*>(.*?)</td>", r" \1 |", storage_html)

    text = re.sub(r"<[^>]+>", " ", storage_html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
```

---

## ❌ Problem 2: Chunking Ignores Document Structure

```python
chunks = chunk_text(text)
```

### 🔥 Fix: Chunk by Headings First

```python
def smart_chunk(text: str):
    sections = re.split(r"\n#{1,3}\s+", text)
    chunks = []

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if len(sec) <= CHUNK_MAX_CHARS:
            chunks.append(sec)
        else:
            chunks.extend(chunk_text(sec))

    return chunks
```

---

## ❌ Problem 3: No Hierarchical Context in Embeddings

### 🔥 Fix: Add Context Before Embedding

```python
contextual_chunks = [
    f"Confluence page: {title}\nSpace: {SPACE_KEY}\nContent:\n{ch}"
    for ch in batch_chunks
]

embeddings = embed_texts(contextual_chunks)
```

---

# 2️⃣ Search & Retrieval Improvements

## ❌ Problem 4: Vector-Only Search

### 🔥 Fix: Hybrid + Semantic Search

```python
results = search_client.search(
    search_text=q,
    vector_queries=[vector_query],
    query_type="semantic",
    semantic_configuration_name="default",
    select=["id", "title", "content", "url", "page_id"]
)
```

---

## ❌ Problem 5: Deduplication Happens Too Early

### 🔥 Fix: Deduplicate After Ranking

```python
final_hits = []
seen_pages = set()

for h in hits:
    pid = h["page_id"]
    if pid not in seen_pages:
        final_hits.append(h)
        seen_pages.add(pid)
```

---

# 3️⃣ Replace Custom Reranker

Delete regex/token-overlap reranking.  
Azure Semantic Reranker is significantly more accurate.

---

# 4️⃣ Query Rewriting (High Impact)

```python
rewrite_prompt = f"""
Rewrite the following user question into a concise search query
for internal Confluence documentation.

User question: {q}
"""

rewritten = client.chat.completions.create(
    model=CHAT_DEPLOYMENT,
    messages=[{"role": "user", "content": rewrite_prompt}],
    temperature=0
).choices[0].message.content.strip()
```

---

# 5️⃣ Stronger System Prompt

> You are a company knowledge assistant.  
> You must answer ONLY using the provided Confluence sources.  
> If the answer is missing or incomplete, say so explicitly.  
> Do not infer or assume information.  
> Prefer step-by-step procedural answers when applicable.

---

# 6️⃣ Azure Semantic Reranker Setup

Add semantic configuration when creating the index:

```python
semantic_config = SemanticConfiguration(
    name="default",
    prioritized_fields={
        "title_field": SemanticField(field_name="title"),
        "content_fields": [SemanticField(field_name="content")],
    },
)
```

⚠️ Requires index recreation.

---

# 7️⃣ Final Backend Search Call

```python
results = search_client.search(
    search_text=search_query,
    vector_queries=[vector_query],
    query_type="semantic",
    semantic_configuration_name="default",
    query_language="en-us",
    top=search_k,
    select=["id", "title", "content", "url", "page_id"]
)
```

---

# 8️⃣ Reindexing Is Mandatory

You must reindex because:
- Chunking changed  
- Table parsing changed  
- Context added to embeddings  

### Safe Rollout Plan
1. Create new index (`confluence-rag-v2`)  
2. Run new ingestion  
3. Update backend config  
4. Test with real queries  
5. Switch traffic  
6. Delete old index  

---

# 🏆 Priority Order of Changes

1. Preserve headings & tables  
2. Smart chunking  
3. Add context to embeddings  
4. Hybrid + semantic search  
5. Query rewriting  
6. Rerank before dedup  
7. Use semantic reranker  
8. Stronger system prompt  

---

# 🎯 Expected Results

- Nested pages understood  
- Tables searchable  
- Better procedural answers  
- Fewer vague or incomplete responses  
- No hallucinations  
- Enterprise-grade RAG performance  
