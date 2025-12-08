import os
import streamlit as st
import asyncio
import glob
from google.genai import types

# 1. IMPORT BACKEND SAFELY
try:
    from backend_agent import auto_runner, FOLDERS, APP_NAME, USER_ID
except ImportError:
    st.error("⚠️ Critical Error: 'backend_agent.py' not found. Please ensure it is in the same folder.")
    st.stop()

# 2. UI CONFIG
st.set_page_config(page_title="Bioprocess AI Lab", layout="wide")
st.title("🧬 Bioprocess AI Assistant")

if "session_id" not in st.session_state:
    st.session_state["session_id"] = "session_" + os.urandom(4).hex()

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

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Lab Bench")
    
    # --- SAFE FILE UPLOAD LOGIC (FIXED) ---
    uploaded_files = st.file_uploader("Upload Data", accept_multiple_files=True)
    saved_paths = []
    
    if uploaded_files:
        st.write("---")
        for up_file in uploaded_files:
            # Define target path
            save_path = os.path.join("input_files", up_file.name)
            
            # 1. Check if file is locked (Permission Check)
            file_is_locked = False
            if os.path.exists(save_path):
                try:
                    # Try to rename file to itself to check lock status
                    os.rename(save_path, save_path)
                except OSError:
                    file_is_locked = True
            
            # 2. Write or Skip
            if file_is_locked:
                st.warning(f"🔒 `{up_file.name}` is in use. Using existing version.")
                saved_paths.append(os.path.abspath(save_path))
            else:
                try:
                    with open(save_path, "wb") as f:
                        f.write(up_file.getbuffer())
                    saved_paths.append(os.path.abspath(save_path))
                    st.caption(f"✅ Saved: `{up_file.name}`")
                except PermissionError:
                    st.error(f"❌ Error: `{up_file.name}` is locked by Windows. Close open files.")
                    # Still append path so AI can try to use it
                    saved_paths.append(os.path.abspath(save_path))

    st.divider()
    
    # --- FILE BROWSER ---
    st.header("💾 Project Files")
    
    # 1. Final Reports
    final_files = glob.glob(os.path.join("final_reports", "*.*"))
    with st.expander("🏆 Final Reports", expanded=True):
        if not final_files: st.caption("No reports yet.")
        for f_path in final_files:
            with open(f_path, "rb") as f:
                st.download_button(f"⬇️ {os.path.basename(f_path)}", f, file_name=os.path.basename(f_path), key=f"dl_{f_path}")

    # 2. Processed Data
    processed_files = glob.glob(os.path.join("processed_files", "*.*"))
    with st.expander("⚙️ Processed Data", expanded=False):
        if not processed_files: st.caption("No processed data yet.")
        for f_path in processed_files:
            with open(f_path, "rb") as f:
                st.download_button(f"⬇️ {os.path.basename(f_path)}", f, file_name=os.path.basename(f_path), key=f"dl_{f_path}")

    st.divider()
    
    # --- CLEAR BUTTON ---
    if st.button("🗑️ Clear All"):
        # Only delete files that are NOT locked
        for folder in FOLDERS.values():
            for f in glob.glob(os.path.join(folder, "*")):
                try: os.remove(f)
                except: pass # Skip locked files silently
        st.session_state["messages"] = []
        st.session_state["session_id"] = "session_" + os.urandom(4).hex()
        st.rerun()

# --- CHAT INTERFACE ---
if "messages" not in st.session_state:
    st.session_state["messages"] = []

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- AGENT EXECUTION ---
user_input = st.chat_input("Ex: 'Clean files and merge them'")

if user_input:
    # 1. Display User Message
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. Prepare Prompt
    full_prompt = user_input
    if saved_paths:
        file_list = "\n".join(saved_paths)
        full_prompt = f"""
[SYSTEM_DATA: The user has uploaded files to the 'input_files' folder. Paths below:]
{file_list}

[USER REQUEST]
{user_input}
"""

    # 3. Define Async Runner
    async def run_agent():
        sess_id = st.session_state["session_id"]
        svc = auto_runner.session_service

        # Ensure Session
        try:
            await svc.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=sess_id)
        except:
            await svc.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=sess_id)

        query = types.Content(role="user", parts=[types.Part(text=full_prompt)])
        msg_ph = st.empty()
        status = st.status("🧠 Processing...", expanded=True)
        full_text = ""
        tools_ran = False

        # Retry Loop for Session Sync Issues
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
                                # Clean up argument display
                                display_args = {k: str(v)[:100] + "..." if len(str(v)) > 100 else v for k, v in args.items()}
                                status.write(f"⚙️ **Running:** `{fname}`")
                                status.json(display_args)
                            if part.function_response:
                                status.write(f"✅ **Done:** `{part.function_response.name}`")
                break 

            except Exception as e:
                if "Session not found" in str(e) and attempt < max_retries - 1:
                    status.write(f"⚠️ Syncing Memory (Attempt {attempt+1})...")
                    await svc.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=sess_id)
                    continue 
                else:
                    st.error(f"Runtime Error: {e}")
                    status.update(label="Failed", state="error")
                    st.stop()

        status.update(label="Complete", state="complete", expanded=False)
        
        if not full_text.strip() and tools_ran:
            full_text = "✅ **Task Completed.** The agent performed actions. Check the sidebar for new files."
            
        msg_ph.markdown(full_text)
        return full_text

    # 4. Run & Save
    with st.chat_message("assistant"):
        response_text = run_async_safe(run_agent())
    
    st.session_state["messages"].append({"role": "assistant", "content": response_text})
    st.rerun()