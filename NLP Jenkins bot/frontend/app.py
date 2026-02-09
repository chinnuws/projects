import streamlit as st
import requests
import time
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="DevOps ChatOps", layout="wide")
st.title("🤖 DevOps ChatOps Assistant")

# ------------------ Session State ------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_params" not in st.session_state:
    st.session_state.pending_params = []

if "current_job" not in st.session_state:
    st.session_state.current_job = None

if "params" not in st.session_state:
    st.session_state.params = {}

if "waiting_for_param" not in st.session_state:
    st.session_state.waiting_for_param = None

# ------------------ Render Chat ------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ------------------ Chat Input (ONLY ONE) ------------------
user_input = st.chat_input("Type your request...")

if user_input:
    # User response to parameter question
    if st.session_state.waiting_for_param:
        param_name = st.session_state.waiting_for_param
        st.session_state.params[param_name] = user_input
        st.session_state.waiting_for_param = None

    else:
        # New user query
        st.session_state.params = {}
        st.session_state.messages.append(
            {"role": "user", "content": user_input}
        )

    # Call backend
    response = requests.post(
        f"{BACKEND_URL}/process",
        json={
            "query": user_input,
            "params": st.session_state.params
        }
    ).json()

    # ------------------ Handle Missing Params ------------------
    if response["type"] == "params":
        st.session_state.pending_params = response["missing"]
        st.session_state.current_job = response["job_name"]

        next_param = st.session_state.pending_params.pop(0)
        st.session_state.waiting_for_param = next_param["name"]

        st.session_state.messages.append({
            "role": "bot",
            "content": f"🔧 {next_param['prompt']}"
        })

    # ------------------ Job Started ------------------
    elif response["type"] == "build_started":
        job_name = response["job_name"]

        st.session_state.messages.append({
            "role": "bot",
            "content": f"🚀 Jenkins job **{job_name}** started. Monitoring status..."
        })

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

    # ------------------ Error / Info ------------------
    else:
        st.session_state.messages.append({
            "role": "bot",
            "content": response.get("message", "⚠️ Something went wrong")
        })
