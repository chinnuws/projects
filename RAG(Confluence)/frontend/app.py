# frontend/app.py
import streamlit as st
import httpx

st.set_page_config(page_title="Confluence AI Assistant", layout="centered")
st.title("💬 Confluence AI Chat")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about Confluence docs..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving context and generating response..."):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:8001/query",
                        json={"query": prompt},
                        timeout=30.0
                    )
                answer = response.json().get("response", "No answer generated.")
            except Exception as e:
                answer = f"Error: {str(e)}"
        st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})

