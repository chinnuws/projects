"""
Streamlit chatbot frontend - Professional Production Design
✅ Fixed: Professional colors & rounded corners everywhere
✅ Fixed: No white box gaps
✅ Fixed: No Streamlit warnings
✅ Fixed: Perfect spacing & aesthetics
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
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================
# SESSION STATE
# ============================================================
if "current_query" not in st.session_state:
    st.session_state.current_query = ""
if "show_results" not in st.session_state:
    st.session_state.show_results = False
if "last_response" not in st.session_state:
    st.session_state.last_response = None

# ============================================================
# PROFESSIONAL CSS - NO WARNINGS
# ============================================================
st.markdown("""
<style>
    /* Global styling - consistent rounded corners */
    * {
        border-radius: 8px !important;
    }
    
    /* Main container - perfect spacing */
    .main {
        padding: 1rem 2rem 2rem 2rem;
        background: #f8fafc;
        min-height: 100vh;
    }
    
    /* Header - professional gradient */
    .header-container {
        text-align: center;
        padding: 2rem;
        margin: -1rem -2rem 2rem -2rem;
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 50%, #1d4ed8 100%);
        border-radius: 12px 12px 0 0;
        color: white;
        box-shadow: 0 4px 20px rgba(59, 130, 246, 0.2);
    }
    
    .header-title {
        font-size: 2.2rem;
        font-weight: 800;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .header-subtitle {
        font-size: 1rem;
        opacity: 0.95;
        margin-top: 0.3rem;
    }
    
    /* Input container - perfect alignment */
    .input-container {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        margin-bottom: 2rem;
        border: 1px solid #e2e8f0;
    }
    
    /* Text input - clean & focused */
    .stTextInput input {
        border: 2px solid #e2e8f0 !important;
        border-radius: 10px !important;
        padding: 1rem 1.2rem !important;
        font-size: 1rem !important;
        box-shadow: none !important;
        height: 52px !important;
    }
    
    .stTextInput input:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important;
    }
    
    /* Search button - perfect icon */
    .stButton > button:first-child {
        background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        height: 52px !important;
        width: 60px !important;
        font-size: 1.3rem !important;
        color: white !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;
    }
    
    .stButton > button:first-child:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 25px rgba(59, 130, 246, 0.4) !important;
    }
    
    /* Clear button */
    .clear-btn {
        background: #f8fafc !important;
        border: 2px solid #e2e8f0 !important;
        color: #64748b !important;
        border-radius: 10px !important;
        height: 48px !important;
        font-weight: 600 !important;
        margin-top: 1rem !important;
    }
    
    .clear-btn:hover {
        background: #f1f5f9 !important;
        border-color: #cbd5e1 !important;
        color: #475569 !important;
    }
    
    /* Question section - NO WHITE BOX */
    .question-section {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        margin-bottom: 1.5rem;
        border: 1px solid #f1f5f9;
    }
    
    /* Answer section - seamless flow */
    .answer-section {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.06);
        margin-bottom: 2rem;
        border: 1px solid #e2e8f0;
    }
    
    .answer-label {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1e40af;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Links section */
    .links-section {
        background: white;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border: 1px solid #e2e8f0;
    }
    
    .links-header {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    .links-subtext {
        color: #64748b;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }
    
    .link-item {
        padding: 1rem;
        margin-bottom: 0.8rem;
        background: #f8fafc;
        border-radius: 10px;
        border-left: 4px solid #3b82f6;
        transition: all 0.2s ease;
        cursor: pointer;
    }
    
    .link-item:hover {
        background: #f1f5f9;
        transform: translateX(4px);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
    }
    
    .link-number {
        font-weight: 700;
        color: #3b82f6;
        font-size: 1.1rem;
        margin-right: 0.8rem;
    }
    
    .link-text {
        color: #1e293b;
        font-weight: 500;
        text-decoration: none;
        font-size: 1rem;
    }
    
    /* Empty state */
    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        color: #64748b;
    }
    
    /* Loading improvements */
    .stSpinner > div > div {
        border-color: #3b82f6;
        border-top-color: transparent;
    }
    
    /* Remove all default margins */
    .stMarkdown {
        margin: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# HEADER
# ============================================================
st.markdown("""
<div class="header-container">
    <h1 class="header-title">📚 Confluence Knowledge Base</h1>
    <p class="header-subtitle">Your guide to organizational documentation</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# MAIN CONTENT
# ============================================================
if st.session_state.show_results and st.session_state.current_query:
    
    # QUESTION SECTION - NO WHITE BOX GAP
    st.markdown(f"""
    <div class="question-section">
        <div style="font-size: 1.1rem; font-weight: 600; color: #475569; margin-bottom: 0.5rem;">
            ❓ Question
        </div>
        <div style="font-size: 1rem; color: #334155;">{st.session_state.current_query}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # API CALL (if needed)
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
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state.show_results = False
                st.stop()
    
    # ANSWER SECTION
    if st.session_state.last_response:
        data = st.session_state.last_response
        
        st.markdown("""
        <div class="answer-section">
            <div class="answer-label">
                💡 Answer
            </div>
        """, unsafe_allow_html=True)
        st.markdown(data.get("answer", "No answer available."))
        st.markdown("</div>", unsafe_allow_html=True)
        
        # RECOMMENDED LINKS (EXACTLY 6)
        if data.get("sources"):
            st.markdown("""
            <div class="links-section">
                <div class="links-header">
                    📚 Recommended Links
                </div>
                <div class="links-subtext">
                    Click to view full documentation
                </div>
            """, unsafe_allow_html=True)
            
            sources = data["sources"][:6]
            
            for idx, source in enumerate(sources, 1):
                title = source.get("title", "Untitled")
                url = source.get("url", "")
                
                if url:
                    st.markdown(f"""
                    <div class="link-item">
                        <span class="link-number">{idx}.</span>
                        <a href="{url}" target="_blank" class="link-text">{title}</a>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="link-item">
                        <span class="link-number">{idx}.</span>
                        <span class="link-text">{title} <em>(No URL)</em></span>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
    
    # Clear button (always visible)
    if st.button("🗑️ Clear", key="clear_results", help="Clear results"):
        st.session_state.current_query = ""
        st.session_state.show_results = False
        st.session_state.last_response = None
        st.rerun()

else:
    # INPUT FORM - Enter key works perfectly
    st.markdown('<div class="input-container">', unsafe_allow_html=True)
    
    with st.form(key="search_form"):
        col1, col2 = st.columns([5, 1])
        
        with col1:
            query_input = st.text_input(
                label="Ask a question",  # ✅ Proper label = no warnings
                placeholder="Type your question here...",
                key="query_input_field"
            )
        
        with col2:
            search_clicked = st.form_submit_button("🔍", use_container_width=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# EMPTY STATE
# ============================================================
if not st.session_state.show_results:
    st.markdown("""
    <div class="empty-state">
        <div style="font-size: 1.4rem; font-weight: 600; color: #475569; margin-bottom: 1rem;">
            💬 Ask anything about our documentation
        </div>
        <div style="font-size: 1rem; color: #64748b; max-width: 500px; margin: 0 auto;">
            Try: "What is our deployment process?" or "How do we handle incidents?"
        </div>
    </div>
    """, unsafe_allow_html=True)
