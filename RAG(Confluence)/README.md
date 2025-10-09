1. Install backend dependencies from requirements.txt
pip install -r requirements.txt

2. Start MCP scraper:
confluence-scraper-mcp --web

3. Start FastAPI backend:
uvicorn backend/app:app --reload

4. Start Streamlit frontend:
streamlit run app.py

Open http://localhost:8501 to access the chatbot.

