import streamlit as st
import os
import asyncio
import pandas as pd
from google.genai import types

# Use auto_runner from the backend
from backend_agent import auto_runner, session_service, APP_NAME, USER_ID

# --- 1. HELPER TO FIX EVENT LOOP (CRITICAL FOR CLOUD RUN) ---
def get_or_create_eventloop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError as ex:
        if "There is no current event loop" in str(ex):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

def run_async_safe(coro):
    """Safely runs an async function in Streamlit."""
    loop = get_or_create_eventloop()
    return loop.run_until_complete(coro)

# --- 2. PAGE CONFIG & SIDEBAR ---
st.set_page_config(page_title="Bioprocess AI Lab", layout="wide")
st.title("🧬 Bioprocess AI Assistant")

with st.sidebar:
    st.header("📂 Lab Bench")
    uploaded_files = st.file_uploader(
        "Drop files here (PDF, Excel, CSV)", 
        accept_multiple_files=True
    )
    
    # Immediate Save Logic
    saved_paths = []
    if uploaded_files:
        if not os.path.exists("temp_uploads"):
            os.makedirs("temp_uploads")
        
        st.success(f"Processing {len(uploaded_files)} files...")
        for up_file in uploaded_files:
            save_path = os.path.join("temp_uploads", up_file.name)
            with open(save_path, "wb") as f:
                f.write(up_file.getbuffer())
            saved_paths.append(os.path.abspath(save_path))
            st.caption(f"✅ Loaded: {up_file.name}")
    
    if st.button("🧹 Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

# --- 3. CHAT INTERFACE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 4. RUN AGENT ---
user_input = st.chat_input("Ex: 'Merge the R06 data with the HPLC results'...")

if user_input:
    # A. Display User Message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # B. Construct Prompt with Explicit Paths
    file_context_str = ""
    if saved_paths:
        file_list_str = "\n".join(saved_paths)
        file_context_str = f"\n\n[SYSTEM: The user has uploaded files at these local paths: {file_list_str}. If PDF, convert first.]"

    # C. Define the Smart Loop (Streaming + Status)
    async def run_agent_turn(prompt):
        try:
            session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
        except:
            session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id="default")

        full_prompt = prompt + file_context_str
        query_content = types.Content(role="user", parts=[types.Part(text=full_prompt)])
        
        full_response_text = ""
        
        # UI Elements
        message_placeholder = st.empty() 
        status_box = st.status("🤖 Agent is thinking...", expanded=True)
        
        async for event in auto_runner.run_async(
            user_id=USER_ID,
            session_id=session.id, 
            new_message=query_content
        ):
            if hasattr(event, 'content') and event.content:
                for part in event.content.parts:
                    # 1. Text Streaming
                    if part.text:
                        full_response_text += part.text
                        message_placeholder.markdown(full_response_text + "▌")
                    
                    # 2. Tool Usage Transparency
                    if hasattr(part, 'function_call') and part.function_call:
                        tool_name = part.function_call.name.replace("_", " ").title()
                        status_box.write(f"🛠️ **Using Tool:** `{tool_name}`")
                        status_box.update(label=f"Running {tool_name}...", state="running")

        # Cleanup
        status_box.update(label="Complete", state="complete", expanded=False)
        message_placeholder.markdown(full_response_text) 
        return full_response_text

    # D. Execute Safely
    with st.chat_message("assistant"):
        final_response = run_async_safe(run_agent_turn(user_input))

    # E. Save Message
    st.session_state.messages.append({"role": "assistant", "content": final_response})

    # F. CHECK FOR DOWNLOADS (Only show buttons if files exist)
    
    # 1. Consolidated Data
    if os.path.exists("Consolidated_Data.xlsx"):
        with open("Consolidated_Data.xlsx", "rb") as f:
            st.download_button(
                label="📥 Download Consolidated Data (XLSX)", 
                data=f, 
                file_name="Consolidated_Data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_consolidated"
            )

    # 2. Formula Sheet
    if os.path.exists("Formula_Reference.docx"):
        with open("Formula_Reference.docx", "rb") as f:
            st.download_button(
                label="📥 Download Formula Sheet (DOCX)", 
                data=f, 
                file_name="Formula_Reference.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="btn_formula"
            )

    # 3. Final Report
    if os.path.exists("Report.docx"):
        with open("Report.docx", "rb") as f:
            st.download_button(
                label="📥 Download Final Report (DOCX)", 
                data=f, 
                file_name="Report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="btn_report"
            )
    
    # STEP 1 RESULT: The Consolidated Data
    if os.path.exists("Consolidated_Data.xlsx"):
        with open("Consolidated_Data.xlsx", "rb") as f:
            st.download_button(
                label="📥 Download Consolidated Data (XLSX)", 
                data=f, 
                file_name="Consolidated_Data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # STEP 2 RESULT: The Formula Sheet
    if os.path.exists("Formula_Reference.docx"):
        with open("Formula_Reference.docx", "rb") as f:
            st.download_button(
                label="📥 Download Formula Sheet (DOCX)", 
                data=f, 
                file_name="Formula_Reference.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

    # STEP 5 RESULT: The Final Report
    if os.path.exists("Report.docx"):
        with open("Report.docx", "rb") as f:
            st.download_button(
                label="📥 Download Final Report (DOCX)", 
                data=f, 
                file_name="Report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )