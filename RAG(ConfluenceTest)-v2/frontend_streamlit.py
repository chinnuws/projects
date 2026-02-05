"""
Simple & Clean Streamlit Frontend
✅ Compact search bar + buttons
✅ Perfect alignment
✅ Enter key works
✅ Clear button works in Kubernetes
✅ No warnings
"""
import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Confluence Knowledge Base",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Session state
if "current_query" not in st.session_state:
    st.session_state.current_query = ""
if "show_results" not in st.session_state:
    st.session_state.show_results = False
if "last_response" not in st.session_state:
    st.session_state.last_response = None

# Clean CSS
st.markdown("""
<style>
    .main { 
        padding: 2rem; 
        max-width: 900px; 
        margin: 0 auto;
    }
    
    /* Simple title */
    .page-title {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 1.5rem;
        text-align: left;
    }
    
    /* Search container - perfect alignment */
    .search-row {
        display: flex;
        gap: 0.5rem;
        align-items: stretch;
        margin-bottom: 0.8rem;
    }
    
    /* Input styling */
    .stTextInput > div > div > input {
        border: 2px solid #cbd5e1 !important;
        border-radius: 8px !important;
        padding: 0.75rem 1rem !important;
        font-size: 1rem !important;
        height: 48px !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important;
    }
    
    /* Buttons - same height as input */
    .stButton > button {
        height: 48px !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0 1.5rem !important;
        border: none !important;
    }
    
    /* Search button */
    div[data-testid="column"]:nth-child(2) button {
        background: #3b82f6 !important;
        color: white !important;
    }
    
    div[data-testid="column"]:nth-child(2) button:hover {
        background: #2563eb !important;
    }
    
    /* Clear button */
    div[data-testid="column"]:nth-child(3) button {
        background: #f1f5f9 !important;
        color: #64748b !important;
        border: 2px solid #cbd5e1 !important;
    }
    
    div[data-testid="column"]:nth-child(3) button:hover {
        background: #e2e8f0 !important;
    }
    
    /* Results sections */
    .result-section {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }
    
    .section-title {
        font-weight: 700;
        font-size: 1.1rem;
        color: #334155;
        margin-bottom: 0.8rem;
    }
    
    /* Link items */
    .link-item {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 1rem;
        margin-bottom: 0.7rem;
        transition: all 0.2s;
    }
    
    .link-item:hover {
        border-color: #3b82f6;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
    }
    
    /* Remove extra spacing */
    .stMarkdown { margin: 0 !important; }
    .block-container { padding-top: 2rem !important; }
</style>
""", unsafe_allow_html=True)

# Simple title
st.markdown('<h1 class="page-title">📚 Confluence Knowledge Base</h1>', unsafe_allow_html=True)

# Search form - perfect alignment
with st.form(key="search_form", clear_on_submit=False):
    col1, col2, col3 = st.columns([6, 1, 1])
    
    with col1:
        query_input = st.text_input(
            "Search",
            placeholder="Ask a question...",
            key="query_field",
            label_visibility="collapsed"
        )
    
    with col2:
        search_btn = st.form_submit_button("🔍", use_container_width=True)
    
    with col3:
        clear_btn = st.form_submit_button("Clear", use_container_width=True)

# Handle search
if search_btn and query_input:
    st.session_state.current_query = query_input.strip()
    st.session_state.show_results = True
    st.session_state.last_response = None

# Handle clear
if clear_btn:
    st.session_state.current_query = ""
    st.session_state.show_results = False
    st.session_state.last_response = None
    st.rerun()

# Results display
if st.session_state.show_results and st.session_state.current_query:
    
    # Question
    st.markdown(f"""
    <div class="result-section">
        <div class="section-title">❓ Question</div>
        <div>{st.session_state.current_query}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # API call
    if st.session_state.last_response is None:
        with st.spinner('Searching...'):
            try:
                resp = requests.post(
                    f"{API_URL}/query",
                    json={"query": st.session_state.current_query},
                    timeout=30
                )
                resp.raise_for_status()
                st.session_state.last_response = resp.json()
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state.show_results = False
    
    # Answer
    if st.session_state.last_response:
        data = st.session_state.last_response
        
        st.markdown("""
        <div class="result-section">
            <div class="section-title">💡 Answer</div>
        """, unsafe_allow_html=True)
        st.markdown(data.get("answer", "No answer found."))
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Links
        if data.get("sources"):
            st.markdown("""
            <div class="result-section">
                <div class="section-title">📚 Recommended Links</div>
            """, unsafe_allow_html=True)
            
            for i, src in enumerate(data["sources"][:6], 1):
                title = src.get("title", "Untitled")
                url = src.get("url", "")
                if url:
                    st.markdown(f"""
                    <div class="link-item">
                        <strong style="color: #3b82f6;">{i}.</strong> 
                        <a href="{url}" target="_blank" style="color: #1e293b; text-decoration: none;">{title}</a>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="link-item">
                        <strong style="color: #94a3b8;">{i}.</strong> 
                        <span style="color: #64748b;">{title}</span>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)

else:
    # Empty state
    st.markdown("""
    <div style="text-align: center; padding: 3rem 0; color: #94a3b8;">
        <p style="font-size: 1.1rem;">Ask anything about our documentation</p>
    </div>
    """, unsafe_allow_html=True)
