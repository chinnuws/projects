# frontend.py (multi-index, fixed experimental_rerun)
import streamlit as st
import requests
from requests.exceptions import RequestException, Timeout

BACKEND_URL = "http://localhost:8000"

st.set_page_config(page_title="RAG Chatbot POC (Multi-Index)", layout="centered")

# -----------------------------
# Session state initialization
# -----------------------------
if "indexes" not in st.session_state:
    st.session_state.indexes = {}
if "active_index" not in st.session_state:
    st.session_state.active_index = None
if "messages" not in st.session_state:
    st.session_state.messages = {}

# Helper to safely rerun if available
def safe_rerun():
    try:
        # old/new streamlit may or may not have this
        st.experimental_rerun()
    except AttributeError:
        # If rerun is not available, do nothing — streamlit will re-run on next interaction
        return

# -----------------------------
# Sidebar: Upload + manage indexes
# -----------------------------
st.sidebar.header("📁 Upload & Manage Indexes")
uploaded_file = st.sidebar.file_uploader("Choose a .txt file", type=["txt"])

if uploaded_file:
    st.sidebar.write(f"Selected: **{uploaded_file.name}**")

    if st.sidebar.button("🚀 Upload & Index"):
        files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
        with st.spinner(f"Uploading and indexing {uploaded_file.name}..."):
            try:
                resp = requests.post(f"{BACKEND_URL}/api/embed_index", files=files, timeout=120)
            except Timeout:
                st.sidebar.error("Upload timed out after 120 seconds. Try a smaller file or check backend logs.")
                resp = None
            except RequestException as e:
                st.sidebar.error(f"Upload failed: {e}")
                resp = None

        if resp is not None:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    idx = data.get("index_name")
                    st.session_state.indexes[idx] = uploaded_file.name
                    st.session_state.active_index = idx
                    st.session_state.messages.setdefault(idx, [])
                    st.sidebar.success(f"Indexed as: **{idx}** ({uploaded_file.name})")
                    st.sidebar.json(data)
                else:
                    st.sidebar.error(f"Indexing failed: {data.get('message')}")
            else:
                st.sidebar.error(f"Upload failed: HTTP {resp.status_code} - {resp.text}")

# -----------------------------
# Sidebar: choose active index
# -----------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("🔎 Choose index to chat with")
if st.session_state.indexes:
    display_list = [f"{name} ({fname})" for name, fname in st.session_state.indexes.items()]
    default_idx = 0
    if st.session_state.active_index:
        full_name = f"{st.session_state.active_index} ({st.session_state.indexes[st.session_state.active_index]})"
        if full_name in display_list:
            default_idx = display_list.index(full_name)
    choice = st.sidebar.selectbox("Indexed documents", display_list, index=default_idx)
    index_lookup = dict(zip(display_list, st.session_state.indexes.keys()))
    st.session_state.active_index = index_lookup[choice]

    if st.sidebar.button("🗑️ Remove selected index (client-side only)"):
        rem_idx = st.session_state.active_index
        st.session_state.indexes.pop(rem_idx, None)
        st.session_state.messages.pop(rem_idx, None)
        st.session_state.active_index = next(iter(st.session_state.indexes), None)
        st.sidebar.success("Removed from session list.")
        # safe_rerun()  # optional: uncomment if you want to attempt explicit rerun

else:
    st.sidebar.info("No indexed documents. Upload a .txt file first.")

st.sidebar.markdown("---")
if st.sidebar.button("🧹 Clear all chat histories"):
    st.session_state.messages = {k: [] for k in st.session_state.messages}
    # safe_rerun()  # optional

# -----------------------------
# Main area: Chat UI
# -----------------------------
st.title("💬 Multi-Document RAG Chatbot")
if st.session_state.active_index:
    idx = st.session_state.active_index
    st.subheader(f"Active Index: **{idx}** — {st.session_state.indexes.get(idx, '')}")

    st.markdown("You are chatting with the selected indexed document. Upload files first to index them.")
    st.session_state.messages.setdefault(idx, [])

    for msg in st.session_state.messages[idx]:
        if msg["role"] == "user":
            st.markdown(f"**You:** {msg['text']}")
        else:
            st.markdown(f"**Bot:** {msg['text']}")

    st.markdown("---")

    user_input = st.text_input("Ask a question about this document:", key=f"input_{idx}")

    col1, col2 = st.columns([4, 1])
    with col1:
        send_clicked = st.button("Send", key=f"send_{idx}")
    with col2:
        clear_clicked = st.button("Clear chat", key=f"clear_{idx}")

    if clear_clicked:
        st.session_state.messages[idx] = []
        # avoid calling experimental_rerun on older streamlit
        safe_rerun()

    if send_clicked and user_input:
        st.session_state.messages[idx].append({"role": "user", "text": user_input})
        with st.spinner("Retrieving relevant context and generating answer..."):
            payload = {"text": user_input, "index_name": idx, "k": 3}
            try:
                resp = requests.post(f"{BACKEND_URL}/api/chat", json=payload, timeout=60)
            except Timeout:
                st.session_state.messages[idx].append({"role": "bot", "text": "Request timed out (60s). Try again."})
                resp = None
            except RequestException as e:
                st.session_state.messages[idx].append({"role": "bot", "text": f"Request failed: {e}"})
                resp = None

        if resp is not None:
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "No answer returned.")
                st.session_state.messages[idx].append({"role": "bot", "text": answer})
                # Commented out context display to hide context from users:
                # if data.get("context_used"):
                #     with st.expander("📖 Context used"):
                #         for i, c in enumerate(data["context_used"], start=1):
                #             st.markdown(f"**Chunk {i}:** {c}")
            else:
                st.session_state.messages[idx].append({"role": "bot", "text": f"Backend error: HTTP {resp.status_code}: {resp.text}"})
else:
    st.warning("Please upload and select a file to start chatting.")

st.markdown("---")
st.caption("🔎 Powered by Azure Cognitive Search + Azure OpenAI (RAG) ⚡")
