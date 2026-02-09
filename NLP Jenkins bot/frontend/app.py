import streamlit as st
import requests
import time
import os

BACKEND_URL = os.getenv("BACKEND_URL")

st.set_page_config(page_title="DevOps ChatOps", layout="wide")

st.title("🤖 DevOps ChatOps Assistant")

# Chat memory
if "messages" not in st.session_state:
    st.session_state.messages = []

if "params" not in st.session_state:
    st.session_state.params = {}

# Render chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
user_input = st.chat_input("Type your request...")

if user_input:
    # User message
    st.session_state.messages.append(
        {"role": "user", "content": user_input}
    )

    with st.chat_message("user"):
        st.markdown(user_input)

    response = requests.post(
        f"{BACKEND_URL}/process",
        json={
            "query": user_input,
            "params": st.session_state.params
        }
    ).json()

    # Parameter collection
    if response["type"] == "params":
        for p in response["missing"]:
            value = st.chat_input(p["prompt"])
            if value:
                st.session_state.params[p["name"]] = value

    # Job started
    elif response["type"] == "build_started":
        job_name = response["job_name"]

        bot_msg = f"🚀 Jenkins job **{job_name}** started. Monitoring status..."
        st.session_state.messages.append(
            {"role": "bot", "content": bot_msg}
        )

        with st.chat_message("bot"):
            status_placeholder = st.empty()

            while True:
                status = requests.get(
                    f"{BACKEND_URL}/status/{job_name}"
                ).json()["status"]

                if status == "RUNNING":
                    status_placeholder.markdown("⏳ Build running...")
                    time.sleep(3)
                else:
                    status_placeholder.markdown(f"✅ Build finished: **{status}**")
                    break

    else:
        st.session_state.messages.append(
            {"role": "bot", "content": response.get("message", "Unknown response")}
        )
