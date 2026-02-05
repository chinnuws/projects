"""
Production-ready Streamlit frontend
✅ Clear button works in Kubernetes
✅ Enter key triggers search
✅ Perfect alignment & professional design
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
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Session state
if "current_query" not in st.session_state:
    st.session_state.current_query = ""
if "show_results" not in st.session_state:
    st.session_state.show_results = False
if "last_response" not in st.session_state:
    st.session_state.last_response = None

# Professional CSS
st.markdown("""
<style>
    /* Perfect layout - no gaps */
    .main { padding: 1.5rem 2rem; background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); }
    
    /* Header */
    .header { 
        background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
        padding: 2rem; 
        border-radius: 16px; 
        text-align: center; 
        color: white; 
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(59, 130, 246, 0.3);
    }
    
    /* Input container - perfect alignment */
    .input-container {
        background: white;
        padding: 1.5rem;
        border-radius: 16px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        border: 1px solid #e2e8f0;
    }
    
    /* Text input */
    .stTextInput > div > div > input {
        border: 2px solid #e2e8f0 !important;
        border-radius: 12px !important;
        padding: 1rem 1.5rem !important;
        height: 56px !important;
        font-size: 1.1rem !important;
    }
    
    /* Search button */
    div[data-testid="column"] button {
        height: 56px !important;
        width: 70px !important;
        border-radius: 12px !important;
        background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
        border: none !important;
        font-size: 1.4rem !important;
        color: white !important;
        box-shadow: 0 4px 20px rgba(59, 130, 246, 0.3) !important;
    }
    
    div[data-testid="column"] button:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%) !important;
        box-shadow: 0 8px 25px rgba(59, 130, 246, 0.4) !important;
    }
    
    /* Clear button - always visible */
    .clear-container {
        margin-top: 1rem;
        text-align: center;
    }
    
    .clear-btn button {
        background: transparent !important;
        border: 2px solid #cbd5e1 !important;
        color: #64748b !important;
        border-radius: 12px !important;
        height: 48px !important;
        padding: 0 2rem !important;
        font-weight: 600 !important;
    }
    
    .clear-btn button:hover {
        border-color: #3b82f6 !important;
        color: #1e40af !important;
        background: rgba(59, 130, 246, 0.05) !important;
    }
    
    /* Results sections */
    .question-box, .answer-box, .links-box {
        background: white;
        border-radius: 16px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border: 1px solid #f1f5f9;
        margin-bottom: 1.5rem;
        padding: 1.8rem;
    }
    
    .section-title {
        font-size: 1.2rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Link items */
    .link-item {
        background: #f8fafc;
        padding: 1.2rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        border-left: 4px solid #3b82f6;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    
    .link-item:hover {
        background: #f1f5f9;
        transform: translateX(4px);
    }
    
    /* Remove all gaps */
    .stMarkdown { margin: 0 !important; }
    hr { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# HEADER
# ============================================================
st.markdown("""
<div class="header">
    <h1 style='margin: 0; font-size: 2.5rem; font-weight: 800;'>📚 Confluence Knowledge Base</h1>
    <p style='margin: 0.5rem 0 0 0; font-size: 1.1rem; opacity: 0.95;'>Your guide to organizational documentation</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# INPUT FORM - Enter key works + Clear button always visible
# ============================================================
st.markdown('<div class="input-container">', unsafe_allow_html=True)

with st.form(key="main_search_form", clear_on_submit=False):
    col1, col2 = st.columns([1, 0.12])
    
    with col1:
        query_input = st.text_input(
            "Ask a question",
            placeholder="Type your question here...",
            key="main_query_input",
            help="Press Enter to search"
        )
    
    with col2:
        submitted = st.form_submit_button("🔍", use_container_width=True)

st.markdown('</div>', unsafe_allow_html=True)

# Clear button - always visible, works in Kubernetes
st.markdown('<div class="clear-container">', unsafe_allow_html=True)
if st.button("🗑️ Clear", key="global_clear_btn"):
    st.session_state.current_query = ""
    st.session_state.show_results = False
    st.session_state.last_response = None
    st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# SEARCH EXECUTION
# ============================================================
if submitted and query_input:
    st.session_state.current_query = query_input.strip()
    st.session_state.show_results = True
    st.session_state.last_response = None

# ============================================================
# RESULTS DISPLAY
# ============================================================
if st.session_state.show_results and st.session_state.current_query:
    
    # Question section
    st.markdown(f"""
    <div class="question-box">
        <div class="section-title">❓ Question</div>
        <div style="font-size: 1.1rem; color: #475569;">{st.session_state.current_query}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # API call
    if st.session_state.last_response is None:
        with st.spinner('🔍 Searching...'):
            try:
                resp = requests.post(f"{API_URL}/query", 
                                   json={"query": st.session_state.current_query}, 
                                   timeout=30)
                resp.raise_for_status()
                st.session_state.last_response = resp.json()
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state.show_results = False
    
    if st.session_state.last_response:
        data = st.session_state.last_response
        
        # Answer
        st.markdown("""
        <div class="answer-box">
            <div class="section-title">💡 Answer</div>
        """, unsafe_allow_html=True)
        st.markdown(data.get("answer", "No answer found."))
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Links - exactly 6
        if data.get("sources"):
            st.markdown("""
            <div class="links-box">
                <div class="section-title">📚 Recommended Links</div>
            """, unsafe_allow_html=True)
            
            for i, source in enumerate(data["sources"][:6], 1):
                title = source.get("title", "Untitled")
                url = source.get("url", "")
                if url:
                    st.markdown(f"""
                    <div class="link-item">
                        <strong style="color: #3b82f6;">{i}.</strong> 
                        <a href="{url}" target="_blank" style="color: #1e40af; text-decoration: none; font-weight: 500;">{title}</a>
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
    <div style="text-align: center; padding: 4rem 2rem; color: #64748b;">
        <div style="font-size: 1.5rem; font-weight: 600; color: #475569; margin-bottom: 1rem;">
            💬 Ask anything about our documentation
        </div>
        <div style="font-size: 1.1rem; max-width: 500px; margin: 0 auto;">
            e.g., "What is our deployment process?" or "How do we handle incidents?"
        </div>
    </div>
    """, unsafe_allow_html=True)
