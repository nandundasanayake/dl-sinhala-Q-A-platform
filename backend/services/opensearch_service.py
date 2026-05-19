# # services/opensearch_service.py
# from opensearchpy import OpenSearch, RequestsHttpConnection
# from config import OPENSEARCH_HOST, OPENSEARCH_PORT, OPENSEARCH_USER, OPENSEARCH_PASS, INDEX_NAME

# opensearch_client = None

# def init_opensearch():
#     """Initialize OpenSearch connection"""
#     global opensearch_client
#     try:
#         opensearch_client = OpenSearch(
#             hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
#             http_auth=(OPENSEARCH_USER, OPENSEARCH_PASS),
#             use_ssl=True,
#             verify_certs=False,
#             connection_class=RequestsHttpConnection,
#             timeout=60,
#             max_retries=5,
#             retry_on_timeout=True,
#             pool_maxsize=20
#         )
#         print("✅ OpenSearch client initialized")
#     except Exception as e:
#         print(f"⚠️ OpenSearch connection failed: {e}")
#         opensearch_client = None

# def setup_opensearch_index():
#     """Ensures the OpenSearch index exists and is configured for k-NN vector search."""
#     if not opensearch_client:
#         return
#     try:
#         if not opensearch_client.indices.exists(index=INDEX_NAME):
#             index_body = {
#                 "settings": {"index.knn": True},
#                 "mappings": {
#                     "properties": {
#                         "video_id": {"type": "keyword"},
#                         "timestamp": {"type": "text"},
#                         "text_chunk": {"type": "text"},
#                         "video_s3_url": {"type": "keyword"},
#                         "transcript_s3_url": {"type": "keyword"},
#                         "duration": {"type": "keyword"},
#                         "embedding": {
#                             "type": "knn_vector",
#                             "dimension": 768
#                         }
#                     }
#                 }
#             }
#             opensearch_client.indices.create(index=INDEX_NAME, body=index_body)
#             print(f"✅ Created OpenSearch Index: {INDEX_NAME}")
#     except Exception as e:
#         print(f"⚠️ OpenSearch Connection Warning: {e}")


# services/opensearch_service.py
import os
import boto3
from requests_aws4auth import AWS4Auth
from opensearchpy import OpenSearch, RequestsHttpConnection
from config import OPENSEARCH_HOST, OPENSEARCH_PORT, OPENSEARCH_USER, OPENSEARCH_PASS, INDEX_NAME
from dotenv import load_dotenv

load_dotenv() 

from config import INDEX_NAME

# Use a module-level dictionary to store the client
_services = {
    'client': None
}

def init_opensearch():
    """Initialize OpenSearch connection based on environment"""
    host = os.getenv("OPENSEARCH_HOST")
    region = os.getenv("AWS_REGION")
    service = 'es'
    
    env = os.getenv("ENVIRONMENT", "production")
    
    try:
        if env == "local":
            auth = (os.getenv("OPENSEARCH_USER"), os.getenv("OPENSEARCH_PASS"))
        else:
            credentials = boto3.Session().get_credentials()
            if credentials is None:
                print("❌ ERROR: IAM Role Credentials not found in boto3!")
            else:
                print(f"✅ IAM Credentials found! Access Key starts with: {credentials.access_key[:5]}...")
            auth = AWS4Auth(region=region, service=service, refreshable_credentials=credentials)

        client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=60,
            max_retries=5,
            retry_on_timeout=True,
            pool_maxsize=20
        )
        _services['client'] = client
        
        if env == "local":
            print(f"✅ OpenSearch client initialized with Basic Auth")
        else:
            print(f"✅ OpenSearch client initialized with IAM role", flush=True)
            
        print(f"   Host: {host}:443")
        return True
    except Exception as e:
        print(f"⚠️ OpenSearch connection failed: {e}")
        _services['client'] = None
        return False

def get_opensearch_client():
    """Get the OpenSearch client instance"""
    return _services['client']

def setup_opensearch_index():
    """Ensures the OpenSearch index exists and is configured for k-NN vector search."""
    client = get_opensearch_client()
    if not client:
        print("⚠️ OpenSearch client not available, skipping index setup")
        return
    try:
        if not client.indices.exists(index=INDEX_NAME):
            index_body = {
                "settings": {
                    "index.knn": True,
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                },
                "mappings": {
                    "properties": {
                        "video_id": {"type": "keyword"},
                        "timestamp": {"type": "text"},
                        "text_chunk": {"type": "text"},
                        "video_s3_url": {"type": "keyword"},
                        "transcript_s3_url": {"type": "keyword"},
                        "duration": {"type": "keyword"},
                        "original_title": {"type": "text"},
                        "thumbnail_url": {"type": "keyword"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": 768,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "faiss"
                            }
                        }
                    }
                }
            }
            client.indices.create(index=INDEX_NAME, body=index_body)
            print(f"✅ Created OpenSearch Index: {INDEX_NAME}")
        else:
            print(f"✅ OpenSearch Index already exists: {INDEX_NAME}")
    except Exception as e:
        print(f"⚠️ OpenSearch Connection Warning: {e}")

# For backward compatibility - create a property
class _OpensearchProxy:
    def __getattr__(self, name):
        client = get_opensearch_client()
        if client is None:
            raise AttributeError("OpenSearch client not initialized")
        return getattr(client, name)

opensearch_client = _OpensearchProxy()