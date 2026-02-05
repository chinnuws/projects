"""
Streamlit chatbot frontend - Professional Design
✅ Fixed: Enter key triggers search
✅ Fixed: 🔍 Search icon (matches screenshot)
✅ Fixed: Exactly 6 recommended links
✅ Removed: Footer tagline
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
    
    /* Input styling - matches screenshot */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 2px solid #e0e0e0;
        padding: 0.75rem 0.75rem 0.75rem 1rem;
        font-size: 1rem;
        background: white;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
    }
    
    /* Button styling - Search button */
    .search-btn > button {
        border-radius: 8px !important;
        font-weight: 600;
        transition: all 0.3s ease;
        border: none;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        height: 42px;
        width: 70px;
    }
    
    .search-btn > button:hover {
        background: linear-gradient(135deg, #5a67d8 0%, #6b46c1 100%) !important;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
    }
    
    /* Clear button */
    .clear-btn > button {
        border-radius: 8px;
        border: 2px solid #e0e0e0;
        background: white;
        color: #666;
        font-weight: 500;
        height: 42px;
    }
    
    .clear-btn > button:hover {
        background: #f7f7f7;
        border-color: #d0d0d0;
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
# SEARCH INPUT WITH ENTER KEY SUPPORT
# ============================================================
# Single row with input + buttons (matches screenshot)
col1, col2 = st.columns([6, 1])

with col1:
    query_input = st.text_input(
        "",
        placeholder="Type your question here...",
        key="query_input_field",
        label_visibility="collapsed",
        help="Press Enter or click 🔍 to search"
    )

with col2:
    search_clicked = st.button("🔍", key="search_btn", help="Search", use_container_width=False)

# Clear button below
clear_clicked = st.button("Clear", key="clear_btn", use_container_width=True)

# ============================================================
# BUTTON HANDLERS (ENTER KEY + CLICK)
# ============================================================
# Enter key OR Search button triggers search
if (search_clicked or st.session_state.get("enter_pressed")) and query_input:
    st.session_state.current_query = query_input.strip()
    st.session_state.show_results = True
    st.session_state.last_response = None
    st.session_state.enter_pressed = False  # Reset

if clear_clicked:
    # Clear all session state
    st.session_state.current_query = ""
    st.session_state.show_results = False
    st.session_state.last_response = None
    st.session_state.enter_pressed = False
    st.rerun()

# ============================================================
# ENTER KEY DETECTION
# ============================================================
if query_input and st.button("", key="dummy", help=""):  # Hidden button for Enter detection
    pass

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
        # SOURCES SECTION (EXACTLY 6 LINKS)
        # ============================================================
        if data.get("sources"):
            st.markdown("### 📚 Recommended Links")
            st.markdown("*Click on the links to view full documentation*")
            st.markdown("")
            
            sources = data["sources"][:6]  # ✅ EXACTLY FIRST 6
            
            for idx, source in enumerate(sources, 1):
                title = source.get("title", "Untitled")
                url = source.get("url", "")
                
                if url:
                    # Create clickable link
                    st.markdown(
                        f"{idx}. [{title}]({url})",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(f"{idx}. {title} *(URL not available)*")
        else:
            st.info("No recommended links found.")

# ============================================================
# EMPTY STATE
# ============================================================
if not st.session_state.show_results:
    st.markdown("""
    <div style="text-align: center; margin-top: 3rem; color: #888;">
        <div style="font-size: 1.2rem; margin-bottom: 1rem;">
            Ask anything about our documentation
        </div>
        <div style="font-size: 0.9rem;">
            e.g., "What is our deployment process?" or "How do we handle incidents?"
        </div>
    </div>
    """, unsafe_allow_html=True)
