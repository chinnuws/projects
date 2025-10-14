"""
Streamlit chatbot frontend - Professional Design
- Beautiful chat interface with enhanced styling
- Professional icons and improved UX
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
    page_title="Knowledge base",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom CSS for professional styling
st.markdown("""
<style>
    /* Main container styling - Lighter background */
    .main {
        background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
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
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.2rem 1.8rem;
        border-radius: 25px 25px 5px 25px;
        margin: 1rem 0;
        display: inline-block;
        max-width: 85%;
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        font-size: 1.05rem;
    }
    
    /* Answer styling - professional white box with dark text */
    .assistant-message {
        background: white;
        color: #1a1a1a;
        padding: 1.8rem;
        border-radius: 25px 25px 25px 5px;
        margin: 1rem 0;
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        line-height: 1.6;
        font-size: 1.05rem;
        border: 1px solid #e0e0e0;
    }
    
    /* Source item styling */
    .source-item {
        background: white;
        padding: 1rem 1.2rem;
        margin: 0.6rem 0;
        border-radius: 12px;
        border-left: 5px solid #667eea;
        box-shadow: 0 3px 6px rgba(0,0,0,0.08);
        transition: all 0.3s ease;
        border: 1px solid #e8e8e8;
    }
    
    .source-item:hover {
        transform: translateX(5px);
        box-shadow: 0 5px 10px rgba(0,0,0,0.12);
        border-left-color: #764ba2;
    }
    
    .source-item a {
        color: #4a5bdc;
        text-decoration: none;
        font-weight: 600;
        font-size: 1.05rem;
    }
    
    .source-item a:hover {
        color: #764ba2;
        text-decoration: underline;
    }
    
    .source-item p {
        color: #444444;
    }
    
    /* Header styling - Compact and centered */
    .header {
        text-align: center;
        color: #2c3e50;
        padding: 1rem 1rem 0.5rem 1rem;
        margin-bottom: 1rem;
    }
    
    .header h1 {
        font-size: 2.2rem;
        margin-bottom: 0.3rem;
        font-weight: 700;
        color: #1a1a1a;
    }
    
    .header p {
        font-size: 1rem;
        font-weight: 400;
        letter-spacing: 0.3px;
        color: #666666;
        margin-bottom: 0.5rem;
    }
    
    /* Icon badges */
    .icon-badge {
        display: inline-block;
        padding: 0.3rem 0.6rem;
        border-radius: 8px;
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
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-size: 1.1rem;
        font-weight: 600;
        margin: 1.5rem 0 1rem 0;
        padding: 0.8rem 1.2rem;
        border-radius: 10px;
        box-shadow: 0 3px 6px rgba(0,0,0,0.1);
    }
    
    /* Search form aligned to right */
    .stForm {
        max-width: 800px;
        margin: 0 0 2rem auto;
    }
    
    /* Remove default Streamlit styling */
    .stTextInput>div>div>input {
        border-radius: 30px;
        padding: 0.8rem 1.5rem;
        font-size: 1rem;
        border: 2px solid #d0d0d0;
        color: #1a1a1a;
    }
    
    .stTextInput>div>div>input::placeholder {
        color: #888888;
    }
    
    .stButton>button {
        border-radius: 30px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.8rem 2rem;
        font-weight: 600;
        font-size: 1rem;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.25);
    }
    
    /* Divider */
    .chat-divider {
        margin: 2rem 0;
        border: none;
        border-top: 2px solid #d0d0d0;
    }
    
    /* Form labels */
    label {
        color: #2c3e50 !important;
    }
    
    /* Video link styling */
    .video-link {
        display: inline-block;
        margin-top: 0.5rem;
        padding: 0.4rem 0.8rem;
        background: #f0f4ff;
        border-radius: 8px;
        border: 1px solid #d0deff;
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

# Header - Compact version
st.markdown('''
<div class="header">
    <h1>📚 Knowledge base</h1>
    <p>💡 Guide to organizational documentation</p>
</div>
''', unsafe_allow_html=True)

# Initialize session state
if "history" not in st.session_state:
    st.session_state.history = []

# Input form - Aligned to the right with spacer column
with st.form("query_form", clear_on_submit=True):
    spacer, col1, col2 = st.columns([1, 4, 1])
    
    with col1:
        query = st.text_input(
            "💬 Your Question", 
            "", 
            placeholder="Type your question here... e.g., 'Onboarding Documentation?'", 
            label_visibility="collapsed"
        )
    
    with col2:
        submitted = st.form_submit_button("🔍 Search", use_container_width=True)
    
    top_k = 5  # Hidden parameter

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
            <strong style="color: #1a1a1a;">💬 Answer:</strong><br/><br/>
            <span style="color: #2c3e50;">{item['answer']}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # Sources with enhanced styling
        if item.get("sources"):
            st.markdown('<div class="resources-header">📖 Related Documentation</div>', unsafe_allow_html=True)
            for i, src in enumerate(item["sources"], 1):
                # Video indicator badge and link
                has_video = src.get("has_video", False)
                video_badge = '<span class="icon-badge video-badge">🎥 Video</span>' if has_video else ""
                
                # Video link section (always show URL if video exists)
                video_link_html = ""
                if has_video:
                    video_link_html = f'<div class="video-link">🎥 <a href="{src["url"]}" target="_blank">Watch Video on this page</a></div>'
                
                # Truncate content preview
                content_preview = src['content'][:180] + "..." if len(src['content']) > 180 else src['content']
                
                st.markdown(f"""
                <div class='source-item'>
                    <strong style="color: #1a1a1a;">📄 {i}. <a href='{src['url']}' target='_blank'>{src['title']}</a></strong>{video_badge}
                    <p style='font-size: 0.95rem; color: #444444; margin-top: 0.5rem; line-height: 1.5;'>{content_preview}</p>
                    {video_link_html}
                </div>
                """, unsafe_allow_html=True)
        
        # Divider between conversations
        if idx < len(st.session_state.history) - 1:
            st.markdown('<hr class="chat-divider">', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
