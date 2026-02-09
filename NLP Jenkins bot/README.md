# DevOps ChatOps Assistant

Trigger Jenkins jobs using natural language queries.

## Tech Stack
- Streamlit (Frontend)
- FastAPI (Backend)
- Azure OpenAI (AI Foundry)
- Jenkins (Job execution)

## Setup

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
