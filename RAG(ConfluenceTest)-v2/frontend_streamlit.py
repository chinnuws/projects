"""
Streamlit chatbot frontend - Professional Design
✅ Fixed: Enter key ACTUALLY triggers search
✅ Improved: Beautiful aesthetics, removed unnecessary gaps
"""
import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Confluence Knowledge Base",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================
if "current_query" not in st.session_state:
    st.session_state.current_query = ""
if "show_results" not in st.session_state:
    st.session_state.show_results = False
if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "trigger_search" not in st.session_state:
    st.session_state.trigger_search = False

# ============================================================
# CUSTOM CSS - IMPROVED AESTHETICS
# ============================================================
st.markdown("""
<style>
    /* Remove default Streamlit padding/margins */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
    }
    
    /* Main container */
    .main {
        padding: 1rem 2rem;
    }
    
    /* Header styling */
    .header-container {
        text-align: center;
        padding: 1.5rem 0;
        margin-bottom: 1.5rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        color: white;
    }
    
    .header-title {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }
    
    .header-subtitle {
        font-size: 1.1rem;
        opacity: 0.9;
    }
    
    /* Remove extra spacing after input */
    .stTextInput {
        margin-bottom: 0rem !important;
    }
    
    /* Input styling - matches screenshot */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 2px solid #e0e0e0;
        padding: 0.75rem 1rem;
        font-size: 1rem;
        background: white;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
    }
    
    /* Button container spacing */
    .button-row {
        margin-top: 0.5rem;
        margin-bottom: 1rem;
    }
    
    /* Search button - gradient with icon */
    div[data-testid="column"]:nth-child(2) button {
        border-radius: 8px !important;
        font-weight: 600;
        border: none;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        height: 50px;
        padding: 0 1.5rem;
        font-size: 1.2rem;
    }
    
    div[data-testid="column"]:nth-child(2) button:hover {
        background: linear-gradient(135deg, #5a67d8 0%, #6b46c1 100%) !important;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
        transform: translateY(-1px);
    }
    
    /* Clear button styling */
    .clear-button button {
        border-radius: 8px;
        border: 2px solid #e0e0e0;
        background: white;
        color: #666;
        font-weight: 500;
        height: 45px;
        width: 100%;
        margin-top: 0.5rem;
    }
    
    .clear-button button:hover {
        background: #f7f7f7;
        border-color: #d0d0d0;
    }
    
    /* Answer box */
    .answer-box {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        margin: 1rem 0;
    }
    
    .answer-label {
        font-weight: 600;
        color: #667eea;
        font-size: 1.1rem;
        margin-bottom: 0.5rem;
    }
    
    /* Question display */
    .question-box {
        background: #ffffff;
        padding: 1rem;
        border-radius: 8px;
        border-left: 3px solid #667eea;
        margin-bottom: 1rem;
        font-weight: 500;
    }
    
    /* Sources section */
    .sources-header {
        font-size: 1.3rem;
        font-weight: 600;
        color: #333;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
    }
    
    .sources-subtext {
        color: #888;
        font-size: 0.9rem;
        margin-bottom: 1rem;
    }
    
    /* Source links - clean list style */
    .source-link-item {
        padding: 0.7rem 1rem;
        margin-bottom: 0.6rem;
        background: white;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        transition: all 0.2s ease;
    }
    
    .source-link-item:hover {
        border-color: #667eea;
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.15);
        transform: translateX(5px);
    }
    
    .source-link-item a {
        color: #667eea;
        text-decoration: none;
        font-weight: 500;
    }
    
    .source-link-item a:hover {
        text-decoration: underline;
    }
    
    /* Loading spinner */
    .stSpinner > div {
        border-color: #667eea;
    }
    
    /* Remove horizontal lines */
    hr {
        margin: 0.5rem 0 !important;
        border-color: #f0f0f0 !important;
    }
    
    /* Empty state styling */
    .empty-state {
        text-align: center;
        margin-top: 3rem;
        color: #888;
    }
    
    .empty-state-title {
        font-size: 1.3rem;
        margin-bottom: 0.8rem;
        color: #555;
    }
    
    .empty-state-subtitle {
        font-size: 0.95rem;
        color: #999;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# HEADER
# ============================================================
st.markdown("""
<div class="header-container">
    <div class="header-title">📚 Confluence Knowledge Base</div>
    <div class="header-subtitle">Your guide to organizational documentation</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# SEARCH INPUT - WITH PROPER ENTER KEY SUPPORT
# ============================================================
with st.form(key="search_form", clear_on_submit=False):
    col1, col2 = st.columns([5, 1])
    
    with col1:
        query_input = st.text_input(
            "",
            placeholder="Type your question here...",
            key="query_input_field",
            label_visibility="collapsed"
        )
    
    with col2:
        search_clicked = st.form_submit_button("🔍", use_container_width=True)

# Clear button outside form
st.markdown('<div class="clear-button">', unsafe_allow_html=True)
clear_clicked = st.button("Clear", key="clear_btn", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# SEARCH TRIGGER (ENTER OR BUTTON)
# ============================================================
if search_clicked and query_input:
    st.session_state.current_query = query_input.strip()
    st.session_state.show_results = True
    st.session_state.last_response = None

if clear_clicked:
    st.session_state.current_query = ""
    st.session_state.show_results = False
    st.session_state.last_response = None
    st.rerun()

# ============================================================
# QUERY PROCESSING & RESULTS
# ============================================================
if st.session_state.show_results and st.session_state.current_query:
    
    # Show the query being processed
    st.markdown(f"""
    <div class="question-box">
        <strong>Question:</strong> {st.session_state.current_query}
    </div>
    """, unsafe_allow_html=True)
    
    # Only make API call if we don't have cached response
    if st.session_state.last_response is None:
        with st.spinner("🔍 Searching knowledge base..."):
            try:
                response = requests.post(
                    f"{API_URL}/query",
                    json={"query": st.session_state.current_query},
                    timeout=30
                )
                response.raise_for_status()
                st.session_state.last_response = response.json()
            except requests.exceptions.Timeout:
                st.error("⏱️ Request timed out. Please try again.")
                st.session_state.show_results = False
                st.stop()
            except requests.exceptions.ConnectionError:
                st.error(f"❌ Could not connect to backend at {API_URL}")
                st.session_state.show_results = False
                st.stop()
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state.show_results = False
                st.stop()
    
    # Display cached response
    if st.session_state.last_response:
        data = st.session_state.last_response
        
        # ============================================================
        # ANSWER SECTION
        # ============================================================
        st.markdown('<div class="answer-box">', unsafe_allow_html=True)
        st.markdown('<div class="answer-label">💡 Answer</div>', unsafe_allow_html=True)
        st.markdown(data.get("answer", "No answer available."))
        st.markdown('</div>', unsafe_allow_html=True)
        
        # ============================================================
        # RECOMMENDED LINKS (EXACTLY 6)
        # ============================================================
        if data.get("sources"):
            st.markdown('<div class="sources-header">📚 Recommended Links</div>', unsafe_allow_html=True)
            st.markdown('<div class="sources-subtext">Click to view full documentation</div>', unsafe_allow_html=True)
            
            sources = data["sources"][:6]  # ✅ EXACTLY 6 MAX
            
            for idx, source in enumerate(sources, 1):
                title = source.get("title", "Untitled")
                url = source.get("url", "")
                
                if url:
                    st.markdown(f"""
                    <div class="source-link-item">
                        {idx}. <a href="{url}" target="_blank">{title}</a>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="source-link-item">
                        {idx}. {title} <em>(URL not available)</em>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("ℹ️ No recommended links found.")

# ============================================================
# EMPTY STATE (WHEN NO SEARCH YET)
# ============================================================
else:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-state-title">
            💬 Ask anything about our documentation
        </div>
        <div class="empty-state-subtitle">
            Try: "What is our deployment process?" or "How do we handle incidents?"
        </div>
    </div>
    """, unsafe_allow_html=True)
