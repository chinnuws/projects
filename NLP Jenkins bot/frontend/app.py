import streamlit as st
import requests
import os

st.set_page_config(page_title="DevOps Chatbot", layout="wide")

st.title("🤖 DevOps ChatOps Assistant")
st.caption("Trigger Jenkins jobs using natural language")

if "params" not in st.session_state:
    st.session_state.params = {}

query = st.text_input("Ask me something", placeholder="Create namespace in AKS cluster")

if st.button("Submit"):
    response = requests.post(
        f"{os.getenv('BACKEND_URL')}/process",
        json={"query": query, "params": st.session_state.params}
    ).json()

    if response["status"] == "need_params":
        st.subheader("🔧 Required Parameters")
        for p in response["missing"]:
            st.session_state.params[p["name"]] = st.text_input(p["prompt"])

    elif response["status"] == "triggered":
        if response["success"]:
            st.success("✅ Jenkins job triggered successfully!")
            st.markdown(f"[📘 Documentation]({response['documentation']})")
        else:
            st.error("❌ Failed to trigger Jenkins job")
