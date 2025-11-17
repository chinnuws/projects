# Kubernetes ConfigMap (k8s/configmap.yaml)

Fenced YAML for the ConfigMap so it renders correctly on GitHub:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: confluence-kb-config
  namespace: confluence-kb
data:
  # Azure Search Configuration
  AZURE_SEARCH_INDEX: "confluence-vector-index"
  
  # API Configuration
  API_URL: "http://confluence-kb-backend:8000"
  
  # Azure Blob Storage Configuration
  BLOB_CONTAINER_NAME: "confluence-state"
  
  # Chunking Configuration
  CHUNK_MAX_CHARS: "3000"
  CHUNK_OVERLAP_CHARS: "400"
  BATCH_SIZE: "32"
```

---

# Kubernetes Secret (k8s/secret.yaml)

Fenced YAML for the Secret:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: confluence-kb-secrets
  namespace: confluence-kb
type: Opaque
stringData:
  # Confluence Configuration
  CONFLUENCE_BASE: "https://your-confluence-instance.atlassian.net"
  CONFLUENCE_USER: "your-confluence-email@domain.com"
  CONFLUENCE_API_TOKEN: "your-confluence-api-token"
  CONFLUENCE_SPACE_KEY: "YOUR-SPACE-KEY"
  
  # Azure Cognitive Search Configuration
  AZURE_SEARCH_ENDPOINT: "https://your-search-service.search.windows.net"
  AZURE_SEARCH_KEY: "your-azure-search-admin-key"
  
  # Azure OpenAI Configuration
  AZURE_OPENAI_ENDPOINT: "https://your-openai-resource.openai.azure.com"
  AZURE_OPENAI_KEY: "your-azure-openai-key"
  AZURE_OPENAI_EMBED_DEPLOYMENT: "text-embedding-ada-002"
  AZURE_OPENAI_CHAT_DEPLOYMENT: "gpt-4"
  
  # Azure Storage Account Configuration
  AZURE_STORAGE_CONNECTION_STRING: "DefaultEndpointsProtocol=https;AccountName=your-storage-account;AccountKey=your-storage-key;EndpointSuffix=core.windows.net"
```

---

# Updated CronJob (k8s/ingest-cronjob.yaml)

Fenced YAML for the CronJob manifest:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: confluence-kb-ingest
  namespace: confluence-kb
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        metadata:
          labels:
            app: confluence-kb-ingest
        spec:
          containers:
          - name: ingest
            image: <your-acr-name>.azurecr.io/confluence-kb-ingest:v1.0.0
            envFrom:
            - configMapRef:
                name: confluence-kb-config
            - secretRef:
                name: confluence-kb-secrets
            resources:
              requests:
                memory: "1Gi"
                cpu: "500m"
              limits:
                memory: "4Gi"
                cpu: "2000m"
          restartPolicy: OnFailure
```

---

# Deployment Commands

Fenced shell block for kubectl commands (renders as commands on GitHub):

```bash
# Create namespace
kubectl create namespace confluence-kb

# Apply ConfigMap
kubectl apply -f k8s/configmap.yaml

# Apply Secrets (make sure to update with real values first!)
kubectl apply -f k8s/secret.yaml

# Verify ConfigMap
kubectl get configmap confluence-kb-config -n confluence-kb -o yaml

# Verify Secret (won't show values)
kubectl get secret confluence-kb-secrets -n confluence-kb

# Apply CronJob
kubectl apply -f k8s/ingest-cronjob.yaml

# Trigger manual job for testing (POSIX shell)
kubectl create job --from=cronjob/confluence-kb-ingest manual-ingest-$(date +%s) -n confluence-kb

# Watch job logs (replace <timestamp> with the job suffix)
kubectl logs -f job/manual-ingest-<timestamp> -n confluence-kb
```
