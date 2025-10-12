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
        color: #1f1f1f;
        padding: 1rem 1.5rem;
        border-radius: 20px 20px 20px 5px;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Recommendation links */
    .recommendation-box {
        background: white;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .recommendation-item {
        padding: 0.5rem 0;
        border-bottom: 1px solid #f0f0f0;
    }
    
    .recommendation-item:last-child {
        border-bottom: none;
    }
    
    .recommendation-item:hover {
        background: #f9f9f9;
        padding-left: 0.5rem;
        transition: all 0.2s;
    }
    
    /* Title styling */
    .main-title {
        text-align: center;
        color: white;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
    }
    
    .subtitle {
        text-align: center;
        color: rgba(255,255,255,0.9);
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    /* Divider */
    .custom-divider {
        height: 1px;
        background: rgba(255,255,255,0.3);
        margin: 1.5rem 0;
    }
    
    /* Input field styling - BLUE ONLY */
    .stTextInput > div > div > input {
        border-radius: 25px;
        border: 2px solid #667eea !important;
        padding: 0.75rem 1.5rem;
        font-size: 1rem;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25) !important;
    }
    
    /* Button styling - BLUE ONLY */
    .stButton > button {
        background: #667eea !important;
        color: white;
        border-radius: 25px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        border: none;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        transition: transform 0.2s;
    }
    
    .stButton > button:hover {
        background: #5568d3 !important;
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.3);
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: #667eea;
    }
    
    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-title">Confluence AI Assistant</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Ask me anything about your Confluence documentation</p>', unsafe_allow_html=True)

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
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    for idx, item in enumerate(reversed(st.session_state.history)):
        # User question
        st.markdown(f"""
            <div class="chat-container">
                <div style="text-align: right;">
                    <div class="user-message">
                        <strong>👤 You:</strong><br/>
                        {item['query']}
                    </div>
                </div>
        """, unsafe_allow_html=True)
        
        # Assistant answer
        st.markdown(f"""
                <div style="text-align: left;">
                    <div class="assistant-message">
                        <strong>🤖 Assistant:</strong><br/>
                        {item['answer']}
                    </div>
                </div>
        """, unsafe_allow_html=True)
        
        # Recommendations
        if item.get("sources"):
            st.markdown('<div class="recommendation-box">', unsafe_allow_html=True)
            st.markdown('<strong>📚 Recommended Resources:</strong>', unsafe_allow_html=True)
            
            for i, s in enumerate(item["sources"], start=1):
                title = s.get("title") or s.get("id") or "Confluence Page"
                url = s.get("url")
                if url and url != "#":
                    st.markdown(f"""
                        <div class="recommendation-item">
                            <a href="{url}" target="_blank" style="text-decoration: none; color: #667eea;">
                                📄 {i}. {title}
                            </a>
                        </div>
                    """, unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        if idx < len(st.session_state.history) - 1:
            st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)

else:
    # Welcome message when no history
    st.markdown("""
        <div style="text-align: center; padding: 3rem; background: white; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h2>👋 Welcome!</h2>
            <p style="color: #666; font-size: 1.1rem;">
                I'm here to help you find information from your Confluence documentation.<br/>
                Ask me anything to get started!
            </p>
            <div style="margin-top: 2rem;">
                <span style="font-size: 3rem;">💡</span>
                <span style="font-size: 3rem; margin: 0 1rem;">📚</span>
                <span style="font-size: 3rem;">🔍</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

# Simplified Sidebar - ONLY Clear Chat History
with st.sidebar:
    st.markdown("---")
    
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.history = []
        st.rerun()
