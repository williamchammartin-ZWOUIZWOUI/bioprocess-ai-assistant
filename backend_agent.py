import os
import sys
import pandas as pd
import json
import re
import logging
import datetime
import pdfplumber
import asyncio
import openpyxl 
import shutil
from docx import Document
from openpyxl import load_workbook, Workbook
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, Reference
from dotenv import load_dotenv
import gc

# Google ADK Imports
from google.adk.agents import LlmAgent, Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools import google_search, AgentTool, preload_memory
from google.adk.sessions import DatabaseSessionService, InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.genai import types
from google.adk.runners import Runner

# --- 1. GLOBAL SETUP ---
load_dotenv()
APP_NAME = "bioprocess_app"
USER_ID = "user_default"

# --- 2. CONFIGURATION & FOLDERS ---
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

FOLDERS = {
    "INPUT": "input_files",
    "PROCESSED": "processed_files",
    "FINAL": "final_reports"
}
for f in FOLDERS.values():
    os.makedirs(f, exist_ok=True)

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

retry_config = types.HttpRetryOptions(
    attempts=10, 
    exp_base=2, 
    initial_delay=15,  # Wait 15s before first retry
    http_status_codes=[429, 500, 503]
)
# --- 3. HELPER FUNCTIONS ---
# (Keep other helpers...)

async def auto_save_to_memory(callback_context):
    """Safely saves session to memory."""
    try:
        # Robust check to prevent NoneType errors
        if not callback_context or not hasattr(callback_context, '_invocation_context'):
            return
            
        ctx = callback_context._invocation_context
        if ctx and hasattr(ctx, 'memory_service') and hasattr(ctx, 'session'):
            if ctx.memory_service and ctx.session:
                await ctx.memory_service.add_session_to_memory(ctx.session)
    except Exception as e:
        # Log warning but DO NOT crash the app
        print(f"[WARN] Memory save skipped: {e}")

def resolve_path(file_path):
    """Smart path finder that looks in specific folders."""
    if not file_path: return None
    clean = file_path.strip('"').strip("'").replace('\\', '/')
    
    # 1. Check if exact path exists
    if os.path.exists(clean): return os.path.abspath(clean)
    
    # 2. Check in specific folders (Priority: Processed -> Input)
    basename = os.path.basename(clean)
    for folder in [FOLDERS["PROCESSED"], FOLDERS["INPUT"]]:
        candidate = os.path.join(folder, basename)
        if os.path.exists(candidate): return os.path.abspath(candidate)
    return None

def smart_read_file(f_path):
    real_path = resolve_path(f_path)
    if not real_path: return pd.DataFrame()
    try:
        if real_path.endswith('.xlsx'): return pd.read_excel(real_path)
        try: return pd.read_csv(real_path, sep=None, engine='python')
        except: return pd.read_csv(real_path, sep=';')
    except: return pd.DataFrame()

def profile_file_content(file_path: str):
    """Returns summary stats of a file. Used by Analyst Agent."""
    try:
        df = smart_read_file(file_path)
        if df.empty: return "Empty file."
        return f"File: {file_path}\nColumns: {list(df.columns)}\nStats:\n{df.describe(include='all').to_string()}"
    except Exception as e: return f"Error: {e}"

# --- 4. THE TOOLKIT ---

def inspect_file_headers(file_path: str):
    try:
        df = smart_read_file(file_path)
        if df.empty: return "Error: Empty."
        return f"FILE: {file_path}\nSHAPE: {df.shape}\nCOLUMNS: {list(df.columns)}\nSAMPLE:\n{df.head(3).to_string()}"
    except Exception as e: return f"Error: {e}"

# --- 4. THE TOOLKIT ---

def inspect_file_headers(file_path: str):
    try:
        df = smart_read_file(file_path)
        if df.empty: return "Error: Empty."
        return f"FILE: {file_path}\nSHAPE: {df.shape}\nCOLUMNS: {list(df.columns)}\nSAMPLE:\n{df.head(3).to_string()}"
    except Exception as e: return f"Error: {e}"

def execute_pandas_operation(file_path: str, operation_description: str, python_code: str):
    """
    Executes dynamic Python code.
    FIX: Uses a single scope to fix 'NameError' and enforces reporting.
    """
    try:
        real_path = resolve_path(file_path)
        if not real_path: return f"Error: File not found."
        print(f"[SYSTEM] 🐍 Executing Python: {operation_description}")
        
        # Load data reliably
        df = smart_read_file(real_path)
        
        # Inject libraries into scope
        import difflib
        import numpy as np
        
        execution_scope = {
            'df': df,
            'pd': pd,
            'np': np,
            'difflib': difflib,
            'datetime': datetime,
            'file_path': real_path
        }
        
        # Execute
        exec(python_code, execution_scope)
        
        # Retrieve result
        if 'df' in execution_scope:
            df_new = execution_scope['df']
        else:
            return "Error: The code did not update the 'df' variable."
        
        # Save
        base_name = os.path.basename(real_path)
        if base_name.endswith(".xlsx"): base_name = base_name.replace(".xlsx", ".csv")
        output_path = os.path.join(FOLDERS["PROCESSED"], base_name)
        
        df_new.to_csv(output_path, index=False)
        
        # CRITICAL FIX: The text in parentheses forces the LLM to speak
        return f"SUCCESS: Processed {base_name}. Saved to {output_path}. (YOU MUST REPORT THIS TO THE USER)"
    except Exception as e: return f"PYTHON ERROR: {e}"

def convert_pdf_to_excel(pdf_path: str, instruction: str = "Extract data"):
    """Converts PDF to CSV. Saves to PROCESSED folder."""
    try:
        real_path = resolve_path(pdf_path)
        if not real_path: return f"Error: Not found."
        if os.path.getsize(real_path) > 10 * 1024 * 1024: return "Error: Too large."
        
        from google import genai
        client = genai.Client(api_key=GOOGLE_API_KEY)
        with open(real_path, "rb") as f: pdf_bytes = f.read()
            
        prompt = f"Task: {instruction}. Output raw CSV. No markdown."
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[types.Content(role="user", parts=[types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), types.Part.from_text(text=prompt)])]
        )
        csv_text = response.text.replace("```csv", "").replace("```", "")
        
        base_name = os.path.basename(real_path).replace(".pdf", "_Converted.csv")
        output_path = os.path.join(FOLDERS["PROCESSED"], base_name)
        
        with open(output_path, "w", encoding="utf-8") as f: f.write(csv_text.strip())
        
        # CRITICAL FIX: Forces reporting
        return f"SUCCESS: Converted {base_name}. Saved to {output_path}. (YOU MUST REPORT THIS TO THE USER)"
    except Exception as e: return f"Error: {e}"

def append_offline_sheet(source_file: str, output_filename: str, sheet_name: str = None):
    """Appends data as a sheet. Saves to FINAL folder."""
    try:
        real_source = resolve_path(source_file)
        if not real_source: return f"Error: Source {source_file} not found."
        
        output_filename = os.path.basename(output_filename)
        output_path = os.path.join(FOLDERS["FINAL"], output_filename)
            
        df = smart_read_file(real_source)
        
        if os.path.exists(output_path):
            with pd.ExcelWriter(output_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df.to_excel(writer, sheet_name=sheet_name or "Data", index=False)
        else:
            with pd.ExcelWriter(output_path, engine='openpyxl', mode='w') as writer:
                df.to_excel(writer, sheet_name=sheet_name or "Data", index=False)
                
        return f"Appended {sheet_name} to {output_path}"
    except Exception as e: return f"Error appending: {e}"

# (Keep add_calculated_column and others as they were)

def append_offline_sheet(source_file: str, output_filename: str, sheet_name: str = None):
    """Appends data as a sheet. Saves to FINAL folder."""
    try:
        real_source = resolve_path(source_file)
        if not real_source: return f"Error: Source {source_file} not found."
        
        output_filename = os.path.basename(output_filename)
        output_path = os.path.join(FOLDERS["FINAL"], output_filename)
            
        df = smart_read_file(real_source)
        
        # Check if file exists to determine mode
        if os.path.exists(output_path):
            # Append Mode: Safe to use if_sheet_exists
            with pd.ExcelWriter(output_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df.to_excel(writer, sheet_name=sheet_name or "Data", index=False)
        else:
            # Write Mode: Create new file (CANNOT use if_sheet_exists)
            with pd.ExcelWriter(output_path, engine='openpyxl', mode='w') as writer:
                df.to_excel(writer, sheet_name=sheet_name or "Data", index=False)
                
        return f"Appended {sheet_name} to {output_path}"
    except Exception as e: return f"Error appending: {e}"

def add_calculated_column(file_path: str, new_col_name: str, formula_template: str):
    """Adds Excel formula column."""
    try:
        clean_path = resolve_path(file_path)
        if not clean_path: return "Error: File not found."
        
        wb = load_workbook(clean_path)
        ws = wb.active 
        col_map = {str(cell.value).strip(): get_column_letter(idx) for idx, cell in enumerate(ws[1], 1) if cell.value}
        new_col_idx = ws.max_column + 1
        ws.cell(row=1, column=new_col_idx, value=new_col_name)
        
        import re
        ingredients = re.findall(r'\{(.*?)\}', formula_template)
        for row in range(2, ws.max_row + 1):
            row_formula = formula_template
            valid = True
            for ing in ingredients:
                if ing in col_map: row_formula = row_formula.replace(f"{{{ing}}}", f"{col_map[ing]}{row}")
                else: valid = False
            if valid: ws.cell(row=row, column=new_col_idx, value=row_formula)
        wb.save(clean_path)
        return f"SUCCESS: Added {new_col_name}"
    except Exception as e: return f"Error: {e}"

def add_bioprocess_analysis(file_path: str, graph_column: str = "Dissolved Oxygen"):
    """Adds graphs."""
    try:
        clean_path = resolve_path(file_path)
        wb = load_workbook(clean_path)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        time_idx = next(i for i, h in enumerate(headers) if h and "Time" in str(h)) + 1
        data_idx = next(i for i, h in enumerate(headers) if h and graph_column in str(h)) + 1
        
        chart = LineChart()
        chart.title = graph_column
        chart.x_axis.title = "Time"
        data = Reference(ws, min_col=data_idx, min_row=1, max_row=ws.max_row)
        cats = Reference(ws, min_col=time_idx, min_row=2, max_row=ws.max_row)
        chart.add_data(data, titles_from_data=True); chart.set_categories(cats)
        ws.add_chart(chart, "E5"); wb.save(clean_path)
        return "SUCCESS: Graph added."
    except Exception as e: return f"Error: {e}"

def create_formula_reference(filename: str, context: str, equations_dict: str, units_dict: str):
    """Creates Formula Doc. Saves to FINAL folder."""
    try:
        if not filename.endswith(".docx"): filename += ".docx"
        output_path = os.path.join(FOLDERS["FINAL"], filename)
        doc = Document(); doc.add_heading('Formula Reference', 0); doc.add_paragraph(context)
        doc.add_paragraph(str(equations_dict))
        doc.save(output_path)
        return f"Created {output_path}"
    except Exception as e: return f"Error: {e}"

def create_word_report(summary: str, filename: str = "Report.docx"):
    """Creates Report. Saves to FINAL folder."""
    try:
        output_path = os.path.join(FOLDERS["FINAL"], filename)
        doc = Document(); doc.add_heading('Final Report', 0); doc.add_paragraph(summary)
        doc.save(output_path)
        return f"Report saved to {output_path}"
    except Exception as e: return f"Error: {e}"

# --- 5. AGENT DEFINITIONS ---

data_wrangler_agent = LlmAgent(
    name="Data_Wrangler_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Cleans data.",
    instruction="""
    You are a Senior Data Scientist / Python Expert.
    
    ### ⚡️ CRITICAL EXECUTION RULES:
    1. **SEQUENTIAL PROCESSING (Avoid 429 Errors):** - Do **NOT** process all 9 files at once. 
       - Process only **1 or 2 files per turn**.
       - After processing 2 files, STOP and report. Wait for the next command.
       
    2. **ROBUST DATE PARSING:** - When parsing timestamps (especially in 'R06...csv'), **ALWAYS** use:
         `pd.to_datetime(df['Timestamp'], dayfirst=True, errors='coerce')`
       - This prevents the "Unknown datetime string format" error.

    3. **DATA LOADING:** The variable `df` contains the file data. Use it directly.
    
    ### 🗣️ MANDATORY OUTPUT RULE (CRITICAL):
    - **NEVER** finish silently (None). 
    - You **MUST** return a text summary: "Processed [File X] and [File Y]. Saved to processed_files/."
    
    ### 🧠 CAPABILITIES:
    - **Fuzzy Matching:** Use `difflib.get_close_matches`.
    - **Filtering:** `df = df[df['Column'].str.contains('R06')]`.
    """,
    tools=[inspect_file_headers, execute_pandas_operation, convert_pdf_to_excel]
)

# 2. The Excel Architect (Robust)
excel_architect_agent = LlmAgent(
    name="Excel_Architect_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Builds Excel.",
    instruction="""
    You are the Master Builder.
    
    ### 🛠️ TASK:
    1. Look for ALL CSV files in `processed_files/`.
    2. Use `append_offline_sheet` to add EACH file as a tab to 'Consolidated_Data.xlsx' in `final_reports/`.
    3. **Important:** Create the 'Online_Data' sheet first if it exists.
    
    ### 🏁 REPORT:
    - Return a text summary of the sheets created.
    """,
    tools=[append_offline_sheet]
)

# 3. The Researcher (Flexible: Formulas + Questions)
research_agent = LlmAgent(
    name="Research_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Performs web searches and compiles formulas.",
    instruction="""
    You are a Scientific Researcher. 
    
    ### 🧠 CAPABILITIES:
    1. **General Research:** If the user asks a question (e.g. "What is a chemostat?"), use `Google Search`.
    2. **Formula Collection:** If the user wants formulas, gather them and use `create_formula_reference` to save to `final_reports/`.
    
    ### ⚡️ RULES:
    - ALWAYS cite your sources (URLs).
    """,
    tools=[google_search, create_formula_reference]
)

formula_agent = LlmAgent(
    name="Excel_Formula_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Adds Excel formulas.",
    instruction="Inject formulas into 'Consolidated_Data.xlsx' using `add_calculated_column`. Check headers first.",
    tools=[add_calculated_column, inspect_file_headers]
)

excel_analyst_agent = LlmAgent(
    name="Excel_Analyst_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Creates graphs.",
    instruction="Ask user what to graph, then use `add_bioprocess_analysis` on the Consolidated Data.",
    tools=[add_bioprocess_analysis, profile_file_content]
)

word_report_agent = LlmAgent(
    name="Word_Report_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Writes report.",
    instruction="Summarize findings into 'Report.docx' in the FINAL folder.",
    tools=[create_word_report]
)

# --- 6. ROOT AGENT (The Project Manager) ---

Bioprocess_agent = LlmAgent(
    name="Bioprocess_Manager",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Manager.",
    instruction="""
    You are the Project Manager.
    
    ### 🗣️ COMMUNICATION:
    - **ANNOUNCE:** "Starting Phase 1...", "Phase 1 Complete. Starting Phase 2..."
    - **NEVER be silent.**
    
    ### 🧠 LOGIC (STRICT MODULAR PIPELINE):
    **SCENARIO A: Raw Files (Do not skip steps)**
    
    1.  **PHASE 1: EXTRACTION (Wrangler)**
        - Call `Data_Wrangler_Agent` to convert PDFs to CSVs.
        - *Wait for confirmation.*
        
    2.  **PHASE 2: CLEANING (Wrangler)**
        - Call `Data_Wrangler_Agent` to clean the CSVs (remove zeros, setpoints).
        - *Wait for confirmation.*
        
    3.  **PHASE 3: MERGING (Wrangler)**
        - Call `Data_Wrangler_Agent` to merge files using 'SampleMap.xlsx'.
        - *Wait for confirmation.*
    
    4.  **PHASE 4: ASSEMBLY (Architect)**
        - Call `Excel_Architect_Agent` to build `final_reports/Consolidated_Data.xlsx`.
        - *Note:* This file is ONLY created in this step.
    
    5.  **PHASE 5: ANALYSIS (Analyst/Researcher)**
        - Call `Research_Agent` for formulas -> `Excel_Formula_Agent` -> `Excel_Analyst_Agent`.
    
    6.  **PHASE 6: REPORTING (Reporter)**
        - Call `Word_Report_Agent`.
    
    **SCENARIO B: Clean Excel**
    - Start at Phase 5.
    
    **SCENARIO C: General Questions**
    - Call `Research_Agent`.
    
    ### 🏁 STATUS UPDATE RULE:
    At the very end of EVERY response, ALWAYS add a status block:
    **Project Status:**
    * 📊 Data: [Pending / Phase 1 / Phase 2 / Phase 3 / ✅ Done]
    * 📝 Report: [Pending / ✅ Done]
    """,
    tools=[
        preload_memory, 
        AgentTool(agent=data_wrangler_agent), 
        AgentTool(agent=excel_architect_agent), 
        AgentTool(agent=research_agent), 
        AgentTool(agent=formula_agent), 
        AgentTool(agent=excel_analyst_agent), 
        AgentTool(agent=word_report_agent)
    ],
    after_agent_callback=auto_save_to_memory
)

# --- 7. RUNNER ---
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()
logging_plugin = LoggingPlugin()

auto_runner = Runner(
    agent=Bioprocess_agent, 
    app_name=APP_NAME, 
    session_service=session_service, 
    memory_service=memory_service, 
    plugins=[logging_plugin]
)