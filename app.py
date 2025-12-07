import streamlit as st
import os
import asyncio
import glob
from google.genai import types

# 1. SETUP FOLDERS
FOLDERS = ["input_files", "processed_files", "final_reports"]
for f in FOLDERS:
    os.makedirs(f, exist_ok=True)

# 2. CACHED BACKEND (Updated to fix Session Bugs)
@st.cache_resource(show_spinner="Loading AI Core...")
def get_backend():
    try:
        # We use importlib to Force-Reload the backend if you change code
        import importlib
        import backend_agent
        importlib.reload(backend_agent)
        return backend_agent.auto_runner, backend_agent.APP_NAME, backend_agent.USER_ID
    except ImportError:
        return None, None, None

# Note: We do NOT import session_service directly anymore to avoid sync issues
auto_runner, APP_NAME, USER_ID = get_backend()

if not auto_runner:
    st.error("⚠️ Error: 'backend_agent.py' not found.")
    st.stop()

# --- HELPER: Async Loop ---
def get_or_create_eventloop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

def run_async_safe(coro):
    loop = get_or_create_eventloop()
    return loop.run_until_complete(coro)

# --- UI CONFIG ---
st.set_page_config(page_title="Bioprocess AI Lab", layout="wide")
st.title("🧬 Bioprocess AI Assistant")

if "session_id" not in st.session_state:
    st.session_state["session_id"] = "session_" + os.urandom(4).hex()

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Lab Bench")
    uploaded_files = st.file_uploader("Upload Data", accept_multiple_files=True)
    saved_paths = []
    
    if uploaded_files:
        st.write("---")
        for up_file in uploaded_files:
            # Save to INPUT folder
            save_path = os.path.join("input_files", up_file.name)
            with open(save_path, "wb") as f:
                f.write(up_file.getbuffer())
            saved_paths.append(os.path.abspath(save_path))
            st.caption(f"📍 `{up_file.name}`")

    st.divider()
    
    # --- ORGANIZED FILE BROWSER ---
    st.header("💾 Project Files")
    
    # 1. Scan Final Reports
    final_files = glob.glob(os.path.join("final_reports", "*.*"))
    with st.expander("🏆 Final Reports", expanded=True):
        if not final_files: st.caption("No reports yet.")
        for f_path in final_files:
            with open(f_path, "rb") as f:
                st.download_button(f"⬇️ {os.path.basename(f_path)}", f, file_name=os.path.basename(f_path), key=f"dl_{f_path}")

    # 2. Scan Processed Files
    processed_files = glob.glob(os.path.join("processed_files", "*.*"))
    with st.expander("⚙️ Processed Data", expanded=False):
        if not processed_files: st.caption("No processed data yet.")
        for f_path in processed_files:
            with open(f_path, "rb") as f:
                st.download_button(f"⬇️ {os.path.basename(f_path)}", f, file_name=os.path.basename(f_path), key=f"dl_{f_path}")

    st.divider()
    if st.button("🗑️ Clear All"):
        for folder in FOLDERS:
            for f in glob.glob(os.path.join(folder, "*")):
                try: os.remove(f)
                except: pass
        st.session_state["messages"] = []
        st.session_state["session_id"] = "session_" + os.urandom(4).hex()
        st.rerun()

# --- CHAT ---
if "messages" not in st.session_state:
    st.session_state["messages"] = []

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- AGENT ---
user_input = st.chat_input("Ex: 'Clean files and merge them for R06'")

if user_input:
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    full_prompt = user_input
    if saved_paths:
        file_list = "\n".join(saved_paths)
        full_prompt = f"""
[SYSTEM_DATA: The user has uploaded files to the 'input_files' folder. Paths below:]
{file_list}

[USER REQUEST]
{user_input}
"""

    async def run_agent():
        sess_id = st.session_state["session_id"]
        
        # 1. GET SERVICE FROM RUNNER (Crucial Fix)
        # We access the service attached to the runner to ensure they are synced
        svc = auto_runner.session_service

        # 2. ENSURE SESSION EXISTS
        try:
            await svc.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=sess_id)
        except:
            await svc.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=sess_id)

        query = types.Content(role="user", parts=[types.Part(text=full_prompt)])
        msg_ph = st.empty()
        status = st.status("🧠 Processing...", expanded=True)
        full_text = ""
        tools_ran = False

        # 3. ROBUST RETRY LOOP
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async for event in auto_runner.run_async(new_message=query, session_id=sess_id, user_id=USER_ID):
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                full_text += part.text
                                msg_ph.markdown(full_text + "▌")
                            if part.function_call:
                                tools_ran = True
                                fname = part.function_call.name
                                args = dict(part.function_call.args)
                                status.write(f"⚙️ **Running:** `{fname}`")
                                status.json(args)
                            if part.function_response:
                                status.write(f"✅ **Done:** `{part.function_response.name}`")
                
                # Success! Break loop
                break 

            except Exception as e:
                # Catch "Session not found" and fix it immediately
                if "Session not found" in str(e) and attempt < max_retries - 1:
                    status.write(f"⚠️ Syncing Memory (Attempt {attempt+1})...")
                    await svc.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=sess_id)
                    continue # Retry
                else:
                    st.error(f"Error: {e}")
                    status.update(label="Failed", state="error")
                    st.stop()

        status.update(label="Complete", state="complete", expanded=False)
        
        # Fallback for silent agent
        if not full_text.strip() and tools_ran:
            full_text = "✅ **Task Completed.** The agent performed actions. Check the sidebar."
            
        msg_ph.markdown(full_text)
        return full_text

    with st.chat_message("assistant"):
        response_text = run_async_safe(run_agent())
    
    st.session_state["messages"].append({"role": "assistant", "content": response_text})
    st.rerun()