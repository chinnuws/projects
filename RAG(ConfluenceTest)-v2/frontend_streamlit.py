import os
import streamlit as st
import requests

# ============================================================
# Config
# ============================================================
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend/query")

st.set_page_config(
    page_title="Confluence Knowledge Assistant",
    layout="centered",
)

st.title("📘 Confluence Knowledge Assistant")

# ============================================================
# Initialize session state (important for AKS)
# ============================================================
if "answer" not in st.session_state:
    st.session_state.answer = None

if "related_docs" not in st.session_state:
    st.session_state.related_docs = []

# ============================================================
# Input
# ============================================================
query = st.text_input(
    "Ask a question",
    key="user_query",
    placeholder="Search Confluence documentation..."
)

# ============================================================
# Buttons
# ============================================================
col1, col2 = st.columns(2)

with col1:
    ask_clicked = st.button("Ask")

with col2:
    clear_clicked = st.button("Clear")

# ============================================================
# Clear logic (AKS-safe)
# ============================================================
if clear_clicked:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ============================================================
# Ask logic
# ============================================================
if ask_clicked and query:
    try:
        with st.spinner("Searching Confluence..."):
            response = requests.post(
                BACKEND_URL,
                json={"query": query},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

        st.session_state.answer = data.get("answer")
        st.session_state.related_docs = data.get("related_docs", [])

    except Exception as e:
        st.error(f"Query failed: {e}")

# ============================================================
# Output
# ============================================================
if st.session_state.answer:
    st.subheader("Answer")
    st.write(st.session_state.answer)

    st.subheader("Related Documentation")
    for doc in st.session_state.related_docs:
        st.markdown(f"- [{doc['title']}]({doc['url']})")
