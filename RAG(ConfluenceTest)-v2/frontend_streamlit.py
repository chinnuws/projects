"""
Streamlit chatbot frontend - Professional Design
Fixed: Clear button for Kubernetes, Top 6 unique page links
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
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ============================================================
# SESSION STATE INITIALIZATION (MUST BE AT TOP)
# ============================================================
if "current_query" not in st.session_state:
    st.session_state.current_query = ""
if "show_results" not in st.session_state:
    st.session_state.show_results = False
if "last_response" not in st.session_state:
    st.session_state.last_response = None

# ============================================================
# CUSTOM CSS
# ============================================================
st.markdown("""
<style>
    /* Main container */
    .main {
        padding: 2rem;
    }
    
    /* Header styling */
    .header-container {
        text-align: center;
        padding: 1.5rem 0;
        margin-bottom: 2rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        color: white;
    }
    
    .header-title {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    
    .header-subtitle {
        font-size: 1.1rem;
        opacity: 0.9;
    }
    
    /* Answer box */
    .answer-box {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        margin: 1.5rem 0;
    }
    
    .answer-label {
        font-weight: 600;
        color: #667eea;
        font-size: 1.1rem;
        margin-bottom: 0.5rem;
    }
    
    /* Sources section */
    .sources-container {
        margin-top: 2rem;
    }
    
    .source-item {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
        border: 1px solid #e0e0e0;
        transition: all 0.3s ease;
    }
    
    .source-item:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        border-color: #667eea;
    }
    
    .source-title {
        font-weight: 600;
        color: #333;
        margin-bottom: 0.3rem;
    }
    
    .source-link {
        color: #667eea;
        text-decoration: none;
        font-weight: 500;
    }
    
    .source-link:hover {
        text-decoration: underline;
    }
    
    /* Input styling */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 2px solid #e0e0e0;
        padding: 0.75rem;
        font-size: 1rem;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
    }
    
    /* Button styling */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    /* Loading spinner */
    .stSpinner > div {
        border-color: #667eea;
    }
    
    /* Error message */
    .error-box {
        background: #fee;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #f44336;
        color: #c62828;
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
# SEARCH INPUT
# ============================================================
col1, col2, col3 = st.columns([6, 1, 1])

with col1:
    query_input = st.text_input(
        "Ask a question",
        placeholder="e.g., What is our deployment process?",
        key="query_input_field",
        label_visibility="collapsed"
    )

with col2:
    search_clicked = st.button("🔍 Search", use_container_width=True, type="primary")

with col3:
    clear_clicked = st.button("Clear", use_container_width=True)

# ============================================================
# BUTTON HANDLERS (FIXED FOR KUBERNETES)
# ============================================================
if search_clicked and query_input:
    st.session_state.current_query = query_input
    st.session_state.show_results = True
    st.session_state.last_response = None  # Clear previous response

if clear_clicked:
    # Clear all session state
    st.session_state.current_query = ""
    st.session_state.show_results = False
    st.session_state.last_response = None
    st.rerun()

# ============================================================
# QUERY PROCESSING
# ============================================================
if st.session_state.show_results and st.session_state.current_query:
    
    # Show the query being processed
    st.markdown(f"**Question:** {st.session_state.current_query}")
    st.markdown("---")
    
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
        st.markdown('<div class="answer-label">Answer:</div>', unsafe_allow_html=True)
        st.markdown(data.get("answer", "No answer available."))
        st.markdown('</div>', unsafe_allow_html=True)
        
        # ============================================================
        # SOURCES SECTION (FIXED: Top 6 unique pages with working links)
        # ============================================================
        if data.get("sources"):
            st.markdown("### 📚 Related Documentation")
            st.markdown("*Click on the links to view full documentation*")
            st.markdown("")
            
            sources = data["sources"]
            
            # Display top 6 unique pages with hyperlinks only
            for idx, source in enumerate(sources[:6], 1):
                title = source.get("title", "Untitled")
                url = source.get("url", "")
                
                if url:
                    # Create clickable link
                    st.markdown(
                        f"{idx}. [{title}]({url})",
                        unsafe_allow_html=True
                    )
                else:
                    # Fallback if URL is missing
                    st.markdown(f"{idx}. {title} *(URL not available)*")
        else:
            st.info("No related documentation found.")

# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #888; font-size: 0.9rem;">
    Powered by Azure AI Search & OpenAI | Data from Confluence
</div>
""", unsafe_allow_html=True)
