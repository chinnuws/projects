# Deployment Guide

This README shows commands and Kubernetes manifests for building, pushing, and deploying the Confluence KB app. Commands and code blocks are fenced so they render correctly on GitHub.

## 1. Build and Push Docker Images

### Login to Azure Container Registry
```bash
az acr login --name <your-acr-name>
```

### Set variables
```bash
ACR_NAME="<your-acr-name>"
IMAGE_TAG="v1.0.0"
```

### Build backend
```bash
docker build -f Dockerfile.backend -t ${ACR_NAME}.azurecr.io/confluence-kb-backend:${IMAGE_TAG} .
```

### Build frontend
```bash
docker build -f Dockerfile.frontend -t ${ACR_NAME}.azurecr.io/confluence-kb-frontend:${IMAGE_TAG} .
```

### Build ingestion job
```bash
docker build -f Dockerfile.ingest -t ${ACR_NAME}.azurecr.io/confluence-kb-ingest:${IMAGE_TAG} .
```

## 2. Push Images
```bash
docker push ${ACR_NAME}.azurecr.io/confluence-kb-backend:${IMAGE_TAG}
docker push ${ACR_NAME}.azurecr.io/confluence-kb-frontend:${IMAGE_TAG}
docker push ${ACR_NAME}.azurecr.io/confluence-kb-ingest:${IMAGE_TAG}
```

## 3. Create Kubernetes Manifests

### ConfigMap for Environment Variables (`k8s/configmap.yaml`)
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: confluence-kb-config
  namespace: confluence-kb
data:
  AZURE_SEARCH_INDEX: "confluence-vector-index"
  API_URL: "http://confluence-kb-backend:8000"
```

### Secret for Sensitive Data (`k8s/secret.yaml`)
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: confluence-kb-secrets
  namespace: confluence-kb
type: Opaque
stringData:
  CONFLUENCE_BASE: "<your-confluence-base-url>"
  CONFLUENCE_USER: "<your-confluence-user>"
  CONFLUENCE_API_TOKEN: "<your-confluence-api-token>"
  CONFLUENCE_SPACE_KEY: "<your-space-key>"
  AZURE_SEARCH_ENDPOINT: "<your-azure-search-endpoint>"
  AZURE_SEARCH_KEY: "<your-azure-search-key>"
  AZURE_OPENAI_ENDPOINT: "<your-azure-openai-endpoint>"
  AZURE_OPENAI_KEY: "<your-azure-openai-key>"
  AZURE_OPENAI_EMBED_DEPLOYMENT: "<your-embed-deployment>"
  AZURE_OPENAI_CHAT_DEPLOYMENT: "<your-chat-deployment>"
```

### Backend Deployment (`k8s/backend-deployment.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: confluence-kb-backend
  namespace: confluence-kb
spec:
  replicas: 2
  selector:
    matchLabels:
      app: confluence-kb-backend
  template:
    metadata:
      labels:
        app: confluence-kb-backend
    spec:
      containers:
      - name: backend
        image: <your-acr-name>.azurecr.io/confluence-kb-backend:v1.0.0
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: confluence-kb-config
        - secretRef:
            name: confluence-kb-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: confluence-kb-backend
  namespace: confluence-kb
spec:
  selector:
    app: confluence-kb-backend
  ports:
  - protocol: TCP
    port: 8000
    targetPort: 8000
  type: ClusterIP
```

### Frontend Deployment (`k8s/frontend-deployment.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: confluence-kb-frontend
  namespace: confluence-kb
spec:
  replicas: 2
  selector:
    matchLabels:
      app: confluence-kb-frontend
  template:
    metadata:
      labels:
        app: confluence-kb-frontend
    spec:
      containers:
      - name: frontend
        image: <your-acr-name>.azurecr.io/confluence-kb-frontend:v1.0.0
        ports:
        - containerPort: 8501
        envFrom:
        - configMapRef:
            name: confluence-kb-config
        resources:
          requests:
            memory: "256Mi"
            cpu: "200m"
          limits:
            memory: "1Gi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: confluence-kb-frontend
  namespace: confluence-kb
spec:
  selector:
    app: confluence-kb-frontend
  ports:
  - protocol: TCP
    port: 8501
    targetPort: 8501
  type: LoadBalancer
```

### Ingestion CronJob (`k8s/ingest-cronjob.yaml`)
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: confluence-kb-ingest
  namespace: confluence-kb
spec:
  schedule: "0 2 * * *"  # Run daily at 2 AM
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
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

### Ingress (`k8s/ingress.yaml`)
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: confluence-kb-ingress
  namespace: confluence-kb
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - confluence-kb.yourdomain.com
    secretName: confluence-kb-tls
  rules:
  - host: confluence-kb.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: confluence-kb-frontend
            port:
              number: 8501
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: confluence-kb-backend
            port:
              number: 8000
```

## 4. Deploy to AKS

### Create namespace
```bash
kubectl create namespace confluence-kb
```

### Apply manifests
```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/ingest-cronjob.yaml
```

### (Optional) Install ingress controller then apply ingress
```bash
kubectl apply -f k8s/ingress.yaml
```

### Check deployment status
```bash
kubectl get pods -n confluence-kb
kubectl get services -n confluence-kb
```

### Run Initial Ingestion (one-time job from CronJob)
```bash
kubectl create job --from=cronjob/confluence-kb-ingest initial-ingest -n confluence-kb
kubectl logs -f job/initial-ingest -n confluence-kb
```

## 5. Monitoring and Scaling

### View logs
```bash
kubectl logs -f deployment/confluence-kb-backend -n confluence-kb
kubectl logs -f deployment/confluence-kb-frontend -n confluence-kb
```

### Check pod status
```bash
kubectl get pods -n confluence-kb -w
```

### Describe resources
```bash
kubectl describe deployment confluence-kb-backend -n confluence-kb
```

### Scale manually
```bash
kubectl scale deployment confluence-kb-backend --replicas=3 -n confluence-kb
kubectl scale deployment confluence-kb-frontend --replicas=3 -n confluence-kb
```

### Horizontal Pod Autoscaler example
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: confluence-kb-backend-hpa
  namespace: confluence-kb
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: confluence-kb-backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## 6. Access the Application

### Get frontend service external IP
```bash
kubectl get service confluence-kb-frontend -n confluence-kb
```

Open a browser to:
```
http://<EXTERNAL-IP>:8501
```

