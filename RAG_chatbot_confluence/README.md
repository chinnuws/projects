# Streamlit
docker build -f Dockerfile.streamlit -t <REG>/confluence-streamlit:latest .
docker push <REG>/confluence-streamlit:latest

# Backend
docker build -f Dockerfile.backend -t <REG>/confluence-backend:latest .
docker push <REG>/confluence-backend:latest

# Ingest
docker build -f Dockerfile.ingest -t <REG>/confluence-ingest:latest .
docker push <REG>/confluence-ingest:latest
