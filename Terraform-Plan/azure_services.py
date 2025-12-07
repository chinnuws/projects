import os
import hashlib
from typing import List, Dict, Any

from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswVectorSearchAlgorithmConfiguration,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticSearch,
)

from openai import AzureOpenAI

load_dotenv()


def _get_search_credential():
    key = os.getenv("AZURE_SEARCH_API_KEY")
    if key:
        return AzureKeyCredential(key)
    return DefaultAzureCredential()


class AzureServices:
    def __init__(self):
        # Azure AI Search config
        self.search_endpoint = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT")
        self.search_index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "terraform-plans")
        self.search_credential = _get_search_credential()

        self.search_client = SearchClient(
            endpoint=self.search_endpoint,
            index_name=self.search_index_name,
            credential=self.search_credential,
        )
        self.index_client = SearchIndexClient(
            endpoint=self.search_endpoint,
            credential=self.search_credential,
        )

        # Azure OpenAI (chat + embeddings)
        self.openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        self.chat_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
        self.embedding_deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

        self.openai_client = AzureOpenAI(
            azure_endpoint=self.openai_endpoint,
            api_key=self.openai_api_key,
            api_version=self.openai_api_version,
        )

    # ---------- Index creation (with vector + semantic search) ----------

    def create_index_if_not_exists(self):
        try:
            self.index_client.get_index(self.search_index_name)
            print(f"Index '{self.search_index_name}' already exists")
            return
        except Exception:
            pass

        # Vector field: 1536 dims for text-embedding-3-small/large.[web:52]
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(name="plan_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="address", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="type", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="name", type=SearchFieldDataType.String),
            SimpleField(name="operation", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="timestamp", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="embedding_hash", type=SearchFieldDataType.String, filterable=True),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=1536,
                vector_search_profile_name="vs-profile",
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[
                HnswVectorSearchAlgorithmConfiguration(
                    name="vs-hnsw",
                    kind="hnsw",
                    parameters={
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500,
                        "metric": VectorSearchAlgorithmMetric.COSINE,
                    },
                )
            ],
            profiles=[
                VectorSearchProfile(
                    name="vs-profile",
                    algorithm_configuration_name="vs-hnsw",
                )
            ],
        )[web:41][web:45]

        semantic_config = SemanticConfiguration(
            name="semantic-config",
            prioritized_fields=SemanticPrioritizedFields(
                title_field=None,
                content_fields=["content"],
            ),
        )

        index = SearchIndex(
            name=self.search_index_name,
            fields=fields,
            vector_search=vector_search,
            semantic_search=SemanticSearch(configurations=[semantic_config]),
        )[web:51][web:54]

        self.index_client.create_index(index)
        print(f"Created index '{self.search_index_name}'")

    # ---------- Embeddings with caching via hash ----------

    def _compute_embedding_hash(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def get_embedding(self, text: str) -> List[float]:
        response = self.openai_client.embeddings.create(
            model=self.embedding_deployment,
            input=text[:8000],
        )[web:52][web:49]
        return response.data[0].embedding

    # ---------- Indexing with delta detection ----------

    def _resource_content_text(self, resource: Dict[str, Any]) -> str:
        return (
            f"Resource type: {resource['type']}. "
            f"Name: {resource['name']}. "
            f"Operation: {resource['operation']}. "
            f"Address: {resource['address']}. "
            f"Details: {resource.get('short_explanation', '')}."
        )

    def _document_id(self, plan_id: str, resource: Dict[str, Any]) -> str:
        # Address may not be unique across plans, so include plan_id
        return f"{plan_id}:{resource['address']}"

    def index_plan_with_embeddings(self, plan_id: str, resources: List[Dict[str, Any]]) -> None:
        to_upload = []
        skipped = 0

        for resource in resources:
            doc_id = self._document_id(plan_id, resource)
            content_text = self._resource_content_text(resource)
            emb_hash = self._compute_embedding_hash(content_text)

            existing = None
            try:
                existing = self.search_client.get_document(doc_id)
            except Exception:
                existing = None

            # If document exists and embedding hash matches, skip recomputation
            if existing and existing.get("embedding_hash") == emb_hash:
                skipped += 1
                continue

            embedding = self.get_embedding(content_text)

            doc = {
                "id": doc_id,
                "plan_id": plan_id,
                "address": resource["address"],
                "type": resource["type"],
                "name": resource["name"],
                "operation": resource["operation"],
                "content": content_text,
                "timestamp": plan_id.split("_")[-1],
                "embedding_hash": emb_hash,
                "content_vector": embedding,
            }

            to_upload.append(doc)

        if to_upload:
            self.search_client.upload_documents(documents=to_upload)
            print(f"Uploaded/updated {len(to_upload)} docs, skipped {skipped} unchanged")
        else:
            print(f"No documents to upload, skipped {skipped} unchanged resources")

    # ---------- AI explanation using chat model ----------

    def explain_plan(self, summary_text: str) -> str:
        from prompts import PLAN_SUMMARY_PROMPT

        formatted = PLAN_SUMMARY_PROMPT.format(summary=summary_text)
        response = self.openai_client.chat.completions.create(
            model=self.chat_deployment,
            messages=[
                {"role": "system", "content": "You are a Terraform infrastructure expert."},
                {"role": "user", "content": formatted},
            ],
            temperature=0.1,
            max_tokens=800,
        )[web:49][web:58]
        return response.choices[0].message.content
