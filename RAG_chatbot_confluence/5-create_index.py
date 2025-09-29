from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SimpleField, SearchableField, SearchFieldDataType, VectorSearch, VectorSearchAlgorithmConfiguration, VectorSearchAlgorithm
)
import os

endpoint = os.getenv("COG_SEARCH_ENDPOINT")
key = os.getenv("COG_SEARCH_ADMIN_KEY")
index_name = os.getenv("COG_SEARCH_INDEX","confluence-index")
credential = AzureKeyCredential(key)
client = SearchIndexClient(endpoint=endpoint, credential=credential)

# define vector configuration
vec_config = VectorSearch(
    algorithm_configurations=[
        VectorSearchAlgorithmConfiguration(
            name="hnsw-config",
            kind="hnsw",
            # you can tune parameters here (M, efConstruction) per docs
            # The SDK model stores algorithm name and default params managed by service
        )
    ]
)

fields = [
    SimpleField(name="id", type=SearchFieldDataType.String, key=True),
    SearchableField(name="title", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
    SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.lucene", searchable=True, retrievable=True),
    SimpleField(name="sourceUrl", type=SearchFieldDataType.String, filterable=True, facetable=False, sortable=False, retrievable=True),
    SimpleField(name="chunkIndex", type=SearchFieldDataType.Int32, filterable=True, retrievable=True),
    SimpleField(name="contentHash", type=SearchFieldDataType.String, filterable=True, retrievable=True),
    SimpleField(name="lastScraped", type=SearchFieldDataType.String, filterable=True, retrievable=True),
    # Vector field
    SimpleField(name="embedding", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), searchable=False, retrievable=False)
]

index = SearchIndex(name=index_name, fields=fields, vector_search=vec_config)
client.create_or_update_index(index)
print("Index created/updated:", index_name)
