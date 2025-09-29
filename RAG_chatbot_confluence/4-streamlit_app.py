import streamlit as st
import requests
from urllib.parse import urljoin

BACKEND = st.secrets.get("backend_url", "http://backend.confluence-chat.svc.cluster.local:8000")

st.set_page_config(page_title="Confluence RAG Chat", layout="centered")
st.title("Confluence Space Chat (space: {})".format(st.secrets.get("space_key","ENG")))

query = st.text_input("Ask a question about the Confluence space:")

if st.button("Ask") and query.strip():
    with st.spinner("Searching..."):
        try:
            r = requests.post(urljoin(BACKEND, "/query"), json={"q": query, "top_k": 5})
            r.raise_for_status()
            j = r.json()
            answer = j.get("answer")
            sources = j.get("sources", [])
            if answer:
                st.subheader("Answer")
                st.write(answer)
            st.subheader("Sources")
            for s in sources:
                st.markdown(f"**{s.get('title')}**  \n{(s.get('url'))}")
                st.write(s.get("content")[:600] + ("..." if len(s.get("content",""))>600 else ""))
        except Exception as e:
            st.error(f"Query failed: {e}")
