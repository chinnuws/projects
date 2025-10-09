#!/bin/bash
# Start MCP server
echo "Starting MCP server..."
uvicorn mcp_server:app --host 0.0.0.0 --port 8000 &

# Start FastAPI backend
echo "Starting FastAPI backend..."
uvicorn backend.app:app --host 0.0.0.0 --port 8001 &

# Start Streamlit frontend
echo "Starting Streamlit frontend..."
streamlit run frontend/app.py --server.port=8501

wait
