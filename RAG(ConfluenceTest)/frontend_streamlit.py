"""
Streamlit chatbot frontend - Clean Design
- Beautiful chat interface with minimal styling
- Sends user's query to FastAPI /api/query
- Displays answer and recommended links
- Keeps chat history in session
"""

import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")

# Page config with custom theme
st.set_page_config(
    page_title="Confluence AI Assistant",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom CSS for clean styling
st.markdown("""
<style>
    /* Main container styling */
    .main {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
    }
    
    /* Remove box backgrounds from responses */
    .chat-container {
        background: transparent;
        padding: 1rem 0;
        margin-bottom: 1rem;
    }
    
    /* Question styling - clean bubble */
    .user-message {
        background: #667eea;
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 20px 20px 5px 20px;
        margin: 1rem 0;
        display: inline-block;
        max-width: 80%;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Answer styling - clean, no background box */
    .assistant-message {
        background: white;
        color: #333;
        padding: 1.5rem;
        border-radius: 20px 20px 20px 5px;
        margin: 1rem 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Source item styling */
    .source-item {
        background: rgba(255,255,255,0.95);
        padding: 0.8rem;
        margin: 0.5rem 0;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .source-item a {
        color: #667eea;
        text-decoration: none;
        font-weight: 600;
    }
    
    .source-item a:hover {
        color: #764ba2;
        text-decoration: underline;
    }
    
    /* Header styling */
    .header {
        text-align: center;
        color: white;
        padding: 2rem 0;
    }
    
    .header h1 {
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    
    .header p {
        font-size: 1.1rem;
        opacity: 0.9;
    }
    
    /* Remove default Streamlit styling */
    .stTextInput>div>div>input {
        border-radius: 25px;
    }
    
    .stButton>button {
        border-radius: 25px;
        background: #667eea;
        color: white;
        border: none;
    }
    
    .stButton>button:hover {
        background: #764ba2;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('''
<div class="header">
    <h1>🤖 Confluence AI Assistant</h1>
    <p>Ask me anything about your Confluence documentation</p>
</div>
''', unsafe_allow_html=True)

# Initialize session state
if "history" not in st.session_state:
    st.session_state.history = []

# Input form
with st.form("query_form", clear_on_submit=True):
    col1, col2 = st.columns([5, 1])
    with col1:
        query = st.text_input("💬 Your Question", "", placeholder="Type your question here...", label_visibility="collapsed")
    with col2:
        submitted = st.form_submit_button("🚀 Ask")
    
    top_k = 5  # Hidden parameter

# Process query
if submitted and query.strip():
    with st.spinner("🔍 Searching knowledge base..."):
        try:
            resp = requests.post(f"{API_URL}/api/query", json={"query": query, "top_k": int(top_k)}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("answer")
            sources = data.get("sources", [])
        except Exception as e:
            st.error(f"❌ Error: {e}")
            answer = None
            sources = []
        
        if answer:
            st.session_state.history.append({"query": query, "answer": answer, "sources": sources})

# Display chat history
if st.session_state.history:
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    for idx, item in enumerate(reversed(st.session_state.history)):
        # User question
        st.markdown(f"""
        <div class="user-message">
            <strong>Q:</strong> {item['query']}
        </div>
        """, unsafe_allow_html=True)
        
        # Assistant answer
        st.markdown(f"""
        <div class="assistant-message">
            <strong>A:</strong> {item['answer']}
        </div>
        """, unsafe_allow_html=True)
        
        # Sources with video indicator
        if item.get("sources"):
            st.markdown("**📚 Recommended Resources:**", unsafe_allow_html=True)
            for i, src in enumerate(item["sources"], 1):
                video_indicator = " 🎥" if src.get("has_video", False) else ""  # NEW: Video indicator
                st.markdown(f"""
                <div class='source-item'>
                    <strong>{i}. <a href='{src['url']}' target='_blank'>{src['title']}{video_indicator}</a></strong>
                    <p style='font-size: 0.9em; color: #666;'>{src['content'][:200]}...</p>
                </div>
                """, unsafe_allow_html=True)
        
        if idx < len(st.session_state.history) - 1:
            st.markdown("<hr style='margin: 2rem 0; border: none; border-top: 1px solid rgba(255,255,255,0.2);'>", unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
else:
    st.markdown("""
    <div style='text-align: center; color: white; padding: 3rem; font-size: 1.1rem;'>
        <p>👋 Welcome!</p>
        <p>I'm here to help you find information from your Confluence documentation.</p>
        <p>Ask me anything to get started!</p>
    </div>
    """, unsafe_allow_html=True)
