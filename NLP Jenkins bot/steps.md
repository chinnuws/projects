
1) Create Azure Redis Cache
```
# Create Azure Redis Cache
az redis create \
  --resource-group <your-rg-name> \
  --name <redis-cache-name> \
  --location <your-location> \
  --sku Standard \
  --vm-size c1 \
  --enable-non-ssl-port false

# Get connection details
az redis show \
  --resource-group <your-rg-name> \
  --name <redis-cache-name>

# Get primary key
az redis list-keys \
  --resource-group <your-rg-name> \
  --name <redis-cache-name>
```

2) Project Structure
```
jenkins-chatbot/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── jenkins_client.py
│   │   ├── intent_parser.py
│   │   └── redis_session.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── k8s/
│   ├── configmap.yaml
│   ├── secrets.yaml
│   ├── backend-deployment.yaml
│   ├── frontend-deployment.yaml
│   └── service.yaml
└── jobs-config.yaml
```

3) Backend Code (FastAPI)
```
### backend/requirements.txt
fastapi==0.109.0
uvicorn==0.27.0
python-jenkins==1.8.2
redis==5.0.1
openai==1.12.0
pydantic==2.6.0
pydantic-settings==2.1.0
python-multipart==0.0.9
PyYAML==6.0.1
requests==2.31.0
```

```
### backend/app/models.py
from pydantic import BaseModel
from typing import Optional, Dict, List

class ChatMessage(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    requires_params: bool = False
    param_names: Optional[List[str]] = None
    job_name: Optional[str] = None
    session_id: str

class JobTriggerRequest(BaseModel):
    session_id: str
    job_name: str
    parameters: Dict[str, str]

class JobTriggerResponse(BaseModel):
    success: bool
    message: str
    build_number: Optional[int] = None
    job_url: Optional[str] = None
```

```
### backend/app/redis_session.py
import redis
import json
import os
from typing import Optional, Dict, Any

class RedisSessionManager:
    def __init__(self):
        redis_host = os.getenv("REDIS_HOST")
        redis_port = int(os.getenv("REDIS_PORT", 6380))
        redis_password = os.getenv("REDIS_PASSWORD")
        
        self.client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            ssl=True,
            decode_responses=True
        )
        self.session_ttl = 3600  # 1 hour
    
    def set_session_data(self, session_id: str, key: str, value: Any):
        """Store session data"""
        session_key = f"session:{session_id}:{key}"
        self.client.setex(
            session_key,
            self.session_ttl,
            json.dumps(value)
        )
    
    def get_session_data(self, session_id: str, key: str) -> Optional[Any]:
        """Retrieve session data"""
        session_key = f"session:{session_id}:{key}"
        data = self.client.get(session_key)
        return json.loads(data) if data else None
    
    def delete_session_data(self, session_id: str, key: str):
        """Delete specific session data"""
        session_key = f"session:{session_id}:{key}"
        self.client.delete(session_key)
    
    def clear_session(self, session_id: str):
        """Clear all session data"""
        pattern = f"session:{session_id}:*"
        for key in self.client.scan_iter(match=pattern):
            self.client.delete(key)
    
    def extend_session(self, session_id: str):
        """Extend session TTL"""
        pattern = f"session:{session_id}:*"
        for key in self.client.scan_iter(match=pattern):
            self.client.expire(key, self.session_ttl)
```

```
### backend/app/jenkins_client.py
import jenkins
import os
from typing import Dict, Optional

class JenkinsJobClient:
    def __init__(self):
        self.jenkins_url = os.getenv("JENKINS_URL")
        self.username = os.getenv("JENKINS_USERNAME")
        self.api_token = os.getenv("JENKINS_API_TOKEN")
        
        self.server = jenkins.Jenkins(
            self.jenkins_url,
            username=self.username,
            password=self.api_token
        )
    
    def trigger_job(self, job_name: str, parameters: Dict[str, str]) -> Dict:
        """Trigger Jenkins job with parameters"""
        try:
            # Get job info to verify it exists
            job_info = self.server.get_job_info(job_name)
            
            # Trigger the build
            queue_number = self.server.build_job(job_name, parameters)
            
            # Get queue item info
            queue_info = self.server.get_queue_item(queue_number)
            
            return {
                "success": True,
                "message": f"Job '{job_name}' triggered successfully",
                "queue_number": queue_number,
                "job_url": f"{self.jenkins_url}/job/{job_name}"
            }
        except jenkins.JenkinsException as e:
            return {
                "success": False,
                "message": f"Failed to trigger job: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Unexpected error: {str(e)}"
            }
    
    def get_build_status(self, job_name: str, build_number: int) -> Dict:
        """Get build status"""
        try:
            build_info = self.server.get_build_info(job_name, build_number)
            return {
                "success": True,
                "building": build_info["building"],
                "result": build_info.get("result", "IN_PROGRESS"),
                "url": build_info["url"]
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }
```

```
### backend/app/intent_parser.py
import os
import yaml
from openai import AzureOpenAI
from typing import Dict, Optional, List

class IntentParser:
    def __init__(self, jobs_config_path: str = "/app/config/jobs-config.yaml"):
        # Initialize Azure OpenAI client
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
        
        # Load jobs configuration
        with open(jobs_config_path, 'r') as f:
            self.jobs_config = yaml.safe_load(f)
    
    def parse_intent(self, user_message: str) -> Dict:
        """Parse user intent using GPT-4o"""
        
        # Create jobs list for context
        jobs_list = "\n".join([
            f"- {job['job_name']}: {job['description']}"
            for job in self.jobs_config['jobs']
        ])
        
        system_prompt = f"""You are an AI assistant that helps users interact with Jenkins jobs.
        
Available Jenkins jobs:
{jobs_list}

Your task is to:
1. Understand the user's intent from their natural language query
2. Identify which Jenkins job they want to execute
3. Extract the job name exactly as specified

Respond ONLY with a JSON object in this format:
{{
    "intent": "execute_job" or "clarification_needed" or "unknown",
    "job_name": "exact job name from the list or null",
    "confidence": 0.0 to 1.0
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=150
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            return {
                "intent": "unknown",
                "job_name": None,
                "confidence": 0.0,
                "error": str(e)
            }
    
    def get_job_config(self, job_name: str) -> Optional[Dict]:
        """Get job configuration"""
        for job in self.jobs_config['jobs']:
            if job['job_name'] == job_name:
                return job
        return None
    
    def get_job_parameters(self, job_name: str) -> List[str]:
        """Get required parameters for a job"""
        job_config = self.get_job_config(job_name)
        if job_config:
            return job_config.get('parameters', [])
        return []
```

```
### backend/app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
from app.models import (
    ChatMessage, ChatResponse, 
    JobTriggerRequest, JobTriggerResponse
)
from app.redis_session import RedisSessionManager
from app.jenkins_client import JenkinsJobClient
from app.intent_parser import IntentParser

app = FastAPI(title="Jenkins Chatbot API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
redis_manager = RedisSessionManager()
jenkins_client = JenkinsJobClient()
intent_parser = IntentParser()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """Handle chat messages and parse intent"""
    try:
        # Extend session TTL
        redis_manager.extend_session(message.session_id)
        
        # Check if we're waiting for parameters
        pending_job = redis_manager.get_session_data(
            message.session_id, 
            "pending_job"
        )
        
        if pending_job:
            # User is providing parameter values
            return await handle_parameter_input(message, pending_job)
        
        # Parse intent using GPT-4o
        intent_result = intent_parser.parse_intent(message.message)
        
        if intent_result["intent"] == "execute_job" and intent_result["job_name"]:
            job_name = intent_result["job_name"]
            job_config = intent_parser.get_job_config(job_name)
            
            if not job_config:
                return ChatResponse(
                    response=f"Job '{job_name}' not found in configuration.",
                    requires_params=False,
                    session_id=message.session_id
                )
            
            parameters = job_config.get("parameters", [])
            
            if parameters:
                # Store pending job info
                redis_manager.set_session_data(
                    message.session_id,
                    "pending_job",
                    {
                        "job_name": job_name,
                        "parameters": parameters,
                        "collected_params": {},
                        "current_param_index": 0
                    }
                )
                
                param_list = "\n".join([f"- {p}" for p in parameters])
                return ChatResponse(
                    response=f"I'll help you execute '{job_name}'. Please provide the following parameters:\n{param_list}\n\nLet's start with: {parameters[0]}",
                    requires_params=True,
                    param_names=parameters,
                    job_name=job_name,
                    session_id=message.session_id
                )
            else:
                # No parameters needed, trigger immediately
                result = jenkins_client.trigger_job(job_name, {})
                return ChatResponse(
                    response=result["message"],
                    requires_params=False,
                    session_id=message.session_id
                )
        
        return ChatResponse(
            response="I couldn't understand your request. Please specify which Jenkins job you'd like to execute. Example: 'Create an AKS cluster' or 'Create namespace'",
            requires_params=False,
            session_id=message.session_id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def handle_parameter_input(message: ChatMessage, pending_job: Dict):
    """Handle parameter collection"""
    params = pending_job["parameters"]
    current_index = pending_job["current_param_index"]
    collected = pending_job["collected_params"]
    
    # Store the current parameter value
    param_name = params[current_index]
    collected[param_name] = message.message
    
    # Move to next parameter
    current_index += 1
    
    if current_index < len(params):
        # More parameters needed
        pending_job["collected_params"] = collected
        pending_job["current_param_index"] = current_index
        redis_manager.set_session_data(
            message.session_id,
            "pending_job",
            pending_job
        )
        
        return ChatResponse(
            response=f"Got it! Now please provide: {params[current_index]}",
            requires_params=True,
            param_names=params,
            job_name=pending_job["job_name"],
            session_id=message.session_id
        )
    else:
        # All parameters collected, trigger job
        job_name = pending_job["job_name"]
        result = jenkins_client.trigger_job(job_name, collected)
        
        # Clear pending job
        redis_manager.delete_session_data(message.session_id, "pending_job")
        
        job_config = intent_parser.get_job_config(job_name)
        doc_link = job_config.get("documentation_link", "N/A")
        
        response_text = f"{result['message']}\n\n"
        if result["success"]:
            response_text += f"Job URL: {result['job_url']}\n"
            response_text += f"Documentation: {doc_link}"
        
        return ChatResponse(
            response=response_text,
            requires_params=False,
            session_id=message.session_id
        )

@app.post("/trigger-job", response_model=JobTriggerResponse)
async def trigger_job(request: JobTriggerRequest):
    """Manually trigger a job with parameters"""
    try:
        result = jenkins_client.trigger_job(
            request.job_name,
            request.parameters
        )
        
        return JobTriggerResponse(
            success=result["success"],
            message=result["message"],
            job_url=result.get("job_url")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

```
### backend/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

4) Frontend Code (Streamlit)
```
### frontend/requirements.txt
streamlit==1.31.0
requests==2.31.0
uuid==1.30
```

```
# frontend/app.py
import streamlit as st
import requests
import uuid

# Configuration
BACKEND_URL = "http://backend-service:8000"

# Initialize session
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

# Page config
st.set_page_config(
    page_title="Jenkins Automation Chatbot",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 Jenkins Automation Chatbot")
st.markdown("Ask me to execute Jenkins jobs in natural language!")

# Sidebar with info
with st.sidebar:
    st.header("Available Commands")
    st.markdown("""
    - Create AKS cluster
    - Create namespace in cluster
    - Create role binding
    - Deploy application
    - And more...
    
    **Session ID:** `{}`
    """.format(st.session_state.session_id[:8]))
    
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("What would you like me to do?"):
    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Send to backend
    with st.chat_message("assistant"):
        with st.spinner("Processing..."):
            try:
                response = requests.post(
                    f"{BACKEND_URL}/chat",
                    json={
                        "session_id": st.session_state.session_id,
                        "message": prompt
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    bot_response = data["response"]
                    st.markdown(bot_response)
                    
                    # Add to chat history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": bot_response
                    })
                else:
                    error_msg = f"Error: {response.status_code} - {response.text}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg
                    })
                    
            except requests.exceptions.RequestException as e:
                error_msg = f"Failed to connect to backend: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg
                })
```

```
### frontend/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

5) Jobs Configuration File
```
### jobs-config.yaml
jobs:
  - job_name: "create-aks-cluster"
    description: "Create a new AKS cluster"
    parameters:
      - "Cluster Name"
      - "Resource Group Name"
      - "Node Count"
      - "VM Size"
    documentation_link: "https://confluence.company.com/aks-cluster-creation"
  
  - job_name: "create-namespace"
    description: "Create a namespace in Kubernetes cluster"
    parameters:
      - "Cluster Name"
      - "Namespace Name"
    documentation_link: "https://confluence.company.com/namespace-creation"
  
  - job_name: "create-rolebinding"
    description: "Create role binding in Kubernetes"
    parameters:
      - "Cluster Name"
      - "Namespace"
      - "Role Name"
      - "Service Account"
    documentation_link: "https://confluence.company.com/rolebinding-creation"
  
  - job_name: "deploy-application"
    description: "Deploy application to AKS"
    parameters:
      - "Application Name"
      - "Cluster Name"
      - "Namespace"
      - "Image Tag"
    documentation_link: "https://confluence.company.com/app-deployment"
```

6) Kubernetes Manifests
```
### k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: jenkins-chatbot-config
  namespace: default
data:
  AZURE_OPENAI_API_VERSION: "2024-02-01"
  AZURE_OPENAI_DEPLOYMENT_NAME: "gpt-4o"
  REDIS_PORT: "6380"
  jobs-config.yaml: |
    jobs:
      - job_name: "create-aks-cluster"
        description: "Create a new AKS cluster"
        parameters:
          - "Cluster Name"
          - "Resource Group Name"
          - "Node Count"
          - "VM Size"
        documentation_link: "https://confluence.company.com/aks-cluster-creation"
      
      - job_name: "create-namespace"
        description: "Create a namespace in Kubernetes cluster"
        parameters:
          - "Cluster Name"
          - "Namespace Name"
        documentation_link: "https://confluence.company.com/namespace-creation"
      
      - job_name: "create-rolebinding"
        description: "Create role binding in Kubernetes"
        parameters:
          - "Cluster Name"
          - "Namespace"
          - "Role Name"
          - "Service Account"
        documentation_link: "https://confluence.company.com/rolebinding-creation"
```

```
### k8s/secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: jenkins-chatbot-secrets
  namespace: default
type: Opaque
stringData:
  AZURE_OPENAI_API_KEY: "your-azure-openai-api-key"
  AZURE_OPENAI_ENDPOINT: "https://your-resource.openai.azure.com/"
  REDIS_HOST: "your-redis-cache.redis.cache.windows.net"
  REDIS_PASSWORD: "your-redis-primary-key"
  JENKINS_URL: "https://your-jenkins-url.com"
  JENKINS_USERNAME: "your-jenkins-username"
  JENKINS_API_TOKEN: "your-jenkins-api-token"
```

```
### k8s/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
      - name: backend
        image: <your-acr>.azurecr.io/jenkins-chatbot-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: AZURE_OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: jenkins-chatbot-secrets
              key: AZURE_OPENAI_API_KEY
        - name: AZURE_OPENAI_ENDPOINT
          valueFrom:
            secretKeyRef:
              name: jenkins-chatbot-secrets
              key: AZURE_OPENAI_ENDPOINT
        - name: AZURE_OPENAI_API_VERSION
          valueFrom:
            configMapKeyRef:
              name: jenkins-chatbot-config
              key: AZURE_OPENAI_API_VERSION
        - name: AZURE_OPENAI_DEPLOYMENT_NAME
          valueFrom:
            configMapKeyRef:
              name: jenkins-chatbot-config
              key: AZURE_OPENAI_DEPLOYMENT_NAME
        - name: REDIS_HOST
          valueFrom:
            secretKeyRef:
              name: jenkins-chatbot-secrets
              key: REDIS_HOST
        - name: REDIS_PORT
          valueFrom:
            configMapKeyRef:
              name: jenkins-chatbot-config
              key: REDIS_PORT
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: jenkins-chatbot-secrets
              key: REDIS_PASSWORD
        - name: JENKINS_URL
          valueFrom:
            secretKeyRef:
              name: jenkins-chatbot-secrets
              key: JENKINS_URL
        - name: JENKINS_USERNAME
          valueFrom:
            secretKeyRef:
              name: jenkins-chatbot-secrets
              key: JENKINS_USERNAME
        - name: JENKINS_API_TOKEN
          valueFrom:
            secretKeyRef:
              name: jenkins-chatbot-secrets
              key: JENKINS_API_TOKEN
        volumeMounts:
        - name: config-volume
          mountPath: /app/config
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
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
      volumes:
      - name: config-volume
        configMap:
          name: jenkins-chatbot-config
          items:
          - key: jobs-config.yaml
            path: jobs-config.yaml
---
apiVersion: v1
kind: Service
metadata:
  name: backend-service
  namespace: default
spec:
  selector:
    app: backend
  ports:
  - protocol: TCP
    port: 8000
    targetPort: 8000
  type: ClusterIP
```

```
### k8s/frontend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
      - name: frontend
        image: <your-acr>.azurecr.io/jenkins-chatbot-frontend:latest
        ports:
        - containerPort: 8501
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /
            port: 8501
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 8501
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-service
  namespace: default
spec:
  selector:
    app: frontend
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8501
  type: LoadBalancer
```

7) Deployment Steps
```
a. Build and Push Docker Images

b. Get AKS Credentials

c. Create Jenkins API Token
Login to Jenkins
Go to User → Configure → API Token
Generate new token and save it.

d. Update Secrets File
Edit k8s/secrets.yaml with your actual values.

e. Deploy to AKS
    # Apply secrets first
    kubectl apply -f k8s/secrets.yaml

    # Apply configmap
    kubectl apply -f k8s/configmap.yaml

    # Deploy backend
    kubectl apply -f k8s/backend-deployment.yaml

    # Deploy frontend
    kubectl apply -f k8s/frontend-deployment.yaml

    # Check deployments
    kubectl get pods
    kubectl get services​

f. Get Frontend URL
    kubectl get service frontend-service
    # Note the EXTERNAL-IP
```

8) Integration Diagram
```
    User → Streamlit (Frontend) → FastAPI (Backend) → GPT-4o (Intent Parsing)
                                        ↓
                                Azure Redis Cache (Session Storage)
                                        ↓
                                Jenkins API (Job Execution)
```


```
### ---------------------------------
Azure Redis Cache Integration Explained
Azure Redis Cache serves as a distributed session store, enabling:
    a. Session Persistence: Chat context survives pod restarts
    b. Multi-Pod Support: Sessions work across backend replicas
​    c. Fast Access: In-memory storage for sub-millisecond response times
    d. Automatic Expiration: TTL-based cleanup of old sessions
The Redis client connects using SSL on port 6380, stores session data as JSON strings with automatic expiration, 
and provides methods to get/set/delete session data.

### ---------------------------------

Jenkins Integration Explained
The Python jenkins library:
    a. Authenticates using username + API token
    b. Triggers jobs via REST API with buildWithParameters endpoint
    c. Passes parameters as dictionary
    d. Returns queue number for tracking
    e. Can poll build status using queue/build numbers

### ---------------------------------
Testing Locally
Create .env file:
    AZURE_OPENAI_API_KEY=your-key
    AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
    AZURE_OPENAI_API_VERSION=2024-02-01
    AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
    REDIS_HOST=localhost
    REDIS_PORT=6379
    REDIS_PASSWORD=
    JENKINS_URL=http://localhost:8080
    JENKINS_USERNAME=admin
    JENKINS_API_TOKEN=your-token


Run locally:
# Terminal 1 - Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Terminal 2 - Frontend
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

``` For local testing, use a local Redis instance or Docker: ```
```
docker run -d -p 6379:6379 redis:latest
```

```
Monitoring with Prometheus
Since your AKS has managed Prometheus, add these annotations to deployments:
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
```

```
This complete solution provides a production-ready chatbot system with natural language understanding, session management, 
and Jenkins automation.
```
