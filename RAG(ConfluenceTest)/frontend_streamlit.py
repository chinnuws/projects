"""
Streamlit chatbot frontend - Professional Design
"""

import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")

# Page config
st.set_page_config(
    page_title="Confluence Knowledge Base",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
<style>
    /* Main container */
    .main {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 2rem;
    }
    
    /* Chat container */
    .chat-container {
        background: transparent;
        padding: 1rem 0;
        margin-bottom: 1rem;
    }
    
    /* Question styling */
    .user-message {
        background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
        color: white;
        padding: 1.2rem 1.8rem;
        border-radius: 20px 20px 5px 20px;
        margin: 1.5rem 0;
        display: inline-block;
        max-width: 85%;
        box-shadow: 0 4px 12px rgba(74, 144, 226, 0.3);
        font-size: 1.05rem;
    }
    
    /* Answer styling */
    .assistant-message {
        background: white;
        color: #2c3e50;
        padding: 1.8rem;
        border-radius: 20px 20px 20px 5px;
        margin: 1.5rem 0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        line-height: 1.7;
        font-size: 1.05rem;
        border: 1px solid #e0e6ed;
    }
    
    /* Source item */
    .source-item {
        background: white;
        padding: 1.2rem 1.5rem;
        margin: 0.8rem 0;
        border-radius: 12px;
        border-left: 4px solid #4a90e2;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        transition: all 0.3s ease;
        border: 1px solid #e8ecef;
    }
    
    .source-item:hover {
        transform: translateX(8px);
        box-shadow: 0 4px 16px rgba(74, 144, 226, 0.15);
        border-left-color: #357abd;
    }
    
    .source-item a {
        color: #4a90e2;
        text-decoration: none;
        font-weight: 600;
        font-size: 1.05rem;
    }
    
    .source-item a:hover {
        color: #357abd;
        text-decoration: underline;
    }
    
    .source-item p {
        color: #5a6c7d;
        margin-top: 0.6rem;
    }
    
    /* Header */
    .header {
        text-align: center;
        padding: 2rem 1rem 1.5rem 1rem;
        margin-bottom: 2rem;
        background: white;
        border-radius: 16px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.06);
    }
    
    .header h1 {
        font-size: 2.8rem;
        margin-bottom: 0.5rem;
        font-weight: 700;
        color: #1a2332;
        background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .header p {
        font-size: 1.1rem;
        font-weight: 400;
        color: #5a6c7d;
        margin-top: 0.5rem;
    }
    
    /* Icon badges */
    .icon-badge {
        display: inline-block;
        padding: 0.3rem 0.7rem;
        border-radius: 6px;
        font-size: 0.85rem;
        margin-left: 0.5rem;
        font-weight: 600;
    }
    
    .video-badge {
        background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
        color: white;
    }
    
    /* Resources header */
    .resources-header {
        background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
        color: white;
        font-size: 1.1rem;
        font-weight: 600;
        margin: 2rem 0 1rem 0;
        padding: 0.9rem 1.3rem;
        border-radius: 10px;
        box-shadow: 0 3px 10px rgba(74, 144, 226, 0.3);
    }
    
    /* Search form */
    .stForm {
        max-width: 700px;
        margin: 0 auto 1rem auto;
    }
    
    /* Search input */
    .stTextInput>div>div>input {
        border-radius: 50px;
        padding: 1rem 1.8rem;
        font-size: 1.05rem;
        border: 2px solid #d0d7de;
        color: #2c3e50;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
    }
    
    .stTextInput>div>div>input:focus {
        border-color: #4a90e2;
        box-shadow: 0 4px 12px rgba(74, 144, 226, 0.2);
    }
    
    .stTextInput>div>div>input::placeholder {
        color: #9ca3af;
    }
    
    /* Search button */
    .stButton>button {
        border-radius: 50px;
        background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
        color: white;
        border: none;
        padding: 1rem 2.5rem;
        font-weight: 600;
        font-size: 1.05rem;
        box-shadow: 0 4px 12px rgba(74, 144, 226, 0.3);
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        background: linear-gradient(135deg, #357abd 0%, #2868a8 100%);
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(74, 144, 226, 0.4);
    }
    
    /* Clear button container */
    .clear-button-container {
        max-width: 700px;
        margin: 0 auto 2.5rem auto;
        text-align: center;
    }
    
    /* Clear button specific styling */
    .clear-button-container .stButton>button {
        background: white;
        color: #6c757d;
        border: 2px solid #e0e6ed;
        padding: 0.7rem 2rem;
        font-size: 0.95rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
    }
    
    .clear-button-container .stButton>button:hover {
        background: #f8f9fa;
        color: #495057;
        border-color: #d0d7de;
        transform: translateY(-1px);
        box-shadow: 0 3px 8px rgba(0,0,0,0.08);
    }
    
    /* Divider */
    .chat-divider {
        margin: 2.5rem 0;
        border: none;
        border-top: 2px solid #e0e6ed;
    }
    
    /* Video link */
    .video-link {
        display: inline-block;
        margin-top: 0.8rem;
        padding: 0.6rem 1rem;
        background: linear-gradient(135deg, #fff5f5 0%, #ffe5e5 100%);
        border-radius: 8px;
        border: 1px solid #ffd0d0;
    }
    
    .video-link a {
        color: #ff6b6b;
        text-decoration: none;
        font-weight: 600;
        font-size: 0.95rem;
    }
    
    .video-link a:hover {
        text-decoration: underline;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('''
<div class="header">
    <h1>📚 Confluence Knowledge Base</h1>
    <p>💡 Your intelligent guide to organizational documentation</p>
</div>
''', unsafe_allow_html=True)

# Initialize session state
if "history" not in st.session_state:
    st.session_state.history = []

# Input form
with st.form("query_form", clear_on_submit=True):
    col1, col2 = st.columns([5, 1])
    
    with col1:
        query = st.text_input(
            "💬 Your Question", 
            "", 
            placeholder="Type your question here... e.g., 'How to onboard new employees?'", 
            label_visibility="collapsed"
        )
    
    with col2:
        submitted = st.form_submit_button("🚀 Search", use_container_width=True)
    
    top_k = 10

# Clear button (outside form, centered below search)
st.markdown('<div class="clear-button-container">', unsafe_allow_html=True)
if st.button("🗑️ Clear", use_container_width=False):
    st.session_state.history = []
    st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# Process query
if submitted and query.strip():
    with st.spinner("🔎 Searching knowledge base..."):
        try:
            resp = requests.post(
                f"{API_URL}/api/query", 
                json={"query": query, "top_k": int(top_k)}, 
                timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("answer")
            sources = data.get("sources", [])
        except Exception as e:
            st.error(f"❌ Error: {e}")
            answer = None
            sources = []
        
        if answer:
            st.session_state.history.append({
                "query": query, 
                "answer": answer, 
                "sources": sources
            })

# Display chat history
if st.session_state.history:
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    for idx, item in enumerate(reversed(st.session_state.history)):
        # User question
        st.markdown(f"""
        <div class="user-message">
            <strong>❓ Question:</strong> {item['query']}
        </div>
        """, unsafe_allow_html=True)
        
        # Assistant answer
        st.markdown(f"""
        <div class="assistant-message">
            <strong style="color: #2c3e50;">💬 Answer:</strong><br/><br/>
            <span style="color: #2c3e50;">{item['answer']}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # Sources
        if item.get("sources"):
            st.markdown('<div class="resources-header">📖 Related Documentation</div>', unsafe_allow_html=True)
            for i, src in enumerate(item["sources"], 1):
                has_video = src.get("has_video", False)
                video_badge = '<span class="icon-badge video-badge">🎥 Video</span>' if has_video else ""
                
                video_link_html = ""
                if has_video:
                    video_link_html = f'<div class="video-link">🎥 <a href="{src["url"]}" target="_blank" rel="noopener noreferrer">Watch Video on this page</a></div>'
                
                content_preview = src['content'][:180] + "..." if len(src['content']) > 180 else src['content']
                
                st.markdown(f"""
                <div class='source-item'>
                    <strong style="color: #2c3e50;">📄 {i}. <a href='{src['url']}' target='_blank' rel='noopener noreferrer'>{src['title']}</a></strong>{video_badge}
                    <p style='font-size: 0.95rem; color: #5a6c7d; margin-top: 0.6rem; line-height: 1.6;'>{content_preview}</p>
                    {video_link_html}
                </div>
                """, unsafe_allow_html=True)
        
        if idx < len(st.session_state.history) - 1:
            st.markdown('<hr class="chat-divider">', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
