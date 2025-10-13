import os
import streamlit as st
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Confluence RAG Chatbot", page_icon="📚", layout="wide")

st.title("📚 Confluence Knowledge Base Chat")
st.markdown("Ask questions about your Confluence documentation")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander("📄 Sources"):
                for source in message["sources"]:
                    video_indicator = "🎥 " if source["has_video"] else ""
                    st.markdown(f"**{video_indicator}[{source['page_title']}]({source['page_url']})** (Score: {source['relevance_score']})")
                    
                    if source["has_video"]:
                        st.info(f"📹 This page contains {source['video_count']} video(s): {', '.join(source['video_filenames'])}")
                    
                    st.caption(source["content_snippet"])
                    st.divider()

# Chat input
if query := st.chat_input("Ask a question..."):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)
    
    # Call API
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    f"{API_URL}/api/query",
                    json={"query": query, "top_k": 5},
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                
                answer = data["answer"]
                sources = data["sources"]
                
                st.markdown(answer)
                
                if sources:
                    with st.expander("📄 Sources"):
                        for source in sources:
                            video_indicator = "🎥 " if source["has_video"] else ""
                            st.markdown(f"**{video_indicator}[{source['page_title']}]({source['page_url']})** (Score: {source['relevance_score']})")
                            
                            if source["has_video"]:
                                st.info(f"📹 This page contains {source['video_count']} video(s): {', '.join(source['video_filenames'])}")
                            
                            st.caption(source["content_snippet"])
                            st.divider()
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "sources": sources
                })
            
            except requests.exceptions.RequestException as e:
                st.error(f"Error connecting to API: {str(e)}")
                st.info(f"Make sure the API is running at {API_URL}")

# Sidebar
with st.sidebar:
    st.header("Settings")
    st.markdown(f"**API Endpoint:** {API_URL}")
    
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()
    
    st.divider()
    st.caption("This chatbot uses RAG to answer questions from your Confluence space.")
