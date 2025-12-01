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
from docx import Document
from openpyxl import load_workbook, Workbook
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, Reference
from dotenv import load_dotenv
import gc

# Google ADK Imports
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import google_search, AgentTool, preload_memory
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.genai import types
from google.adk.runners import Runner

# --- 1. GLOBAL SETUP (Required for app.py) ---
load_dotenv()
APP_NAME = "bioprocess_app"
USER_ID = "user_default"
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

# --- 2. CONFIGURATION ---
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

retry_config = types.HttpRetryOptions(attempts=3)
KNOWLEDGE_FILE = "bioprocess_knowledge.json"

# --- FULL KNOWLEDGE BASE (Restored from Original) ---

DEFAULT_ONLINE = {
    "Time_Hours": ["time", "timer", "timestamp", "duration", "process time"],
    "Temperature [C]": ["temp", "t°", "deg c", "heating"],
    "pH": ["ph ", "ph_", "ph-value"], 
    "DO_Percent [%]": ["do ", "po2", "oxygen", "dissolved", "dot"],
    "Pressure [bar]": ["press", "bar", "psi", "headspace"],
    "Stirring_Speed [rpm]": ["stir", "agit", "rpm", "speed", "mix"],
    "Torque": ["torque", "nm"],
    "Power_Input": ["power", "watt", "p/v"],
    "Air_Flow": ["air", "flow", "aeration", "sparge"],
    "O2_Flow": ["o2 flow", "oxygen flow"],
    "N2_Flow": ["n2 flow", "nitrogen"],
    "CO2_Flow": ["co2 flow", "carbon dioxide flow"],
    "Gas_Overlay": ["overlay", "headspace flow"],
    "Offgas_CO2": ["co2", "carbon diox", "offgas co2", "xco2"],
    "Offgas_O2": ["o2", "oxygen out", "offgas o2", "xo2"],
    "OUR": ["our", "oxygen uptake"],
    "CER": ["cer", "carbon evolution"],
    "RQ": ["rq", "respiratory"],
    "Feed_Rate": ["feed", "pump", "addition", "substrate"],
    "Feed_Total": ["feed total", "feed vol", "feed acc"],
    "Base_Total": ["base", "naoh", "alkali"],
    "Acid_Total": ["acid", "hcl", "h3po4"],
    "Antifoam": ["antifoam", "af"],
    "Weight": ["weight", "mass", "kg", "scale"],
    "Volume": ["volume", "working vol", "l"],
    "Conductivity": ["cond", "ms/cm"],
    "Capacitance": ["cap", "biomass", "permittivity", "aber", "fogale"],
    "Turbidity": ["turb", "od", "optical"]
}

DEFAULT_OFFLINE = {
    "VCD": ["vcd", "viable", "cell density", "living cells", "xv"],
    "TCD": ["tcd", "total cells"],
    "Viability [%]": ["viab", "%", "alive"],
    "Diameter": ["diam", "size", "um"],
    "Glucose": ["glc", "gluc", "sugar"],
    "Glutamine": ["gln", "glutamine"],
    "Glutamate": ["glu", "glutamate"],
    "Lactate": ["lac", "lactate"],
    "Ammonium": ["amm", "nh4", "nh3"],
    "LDH": ["ldh"],
    "Offline_pH": ["off ph", "offline ph", "ph_off"],
    "Osmolality": ["osmo", "mosm"],
    "Titer": ["titer", "product", "igg", "concentration", "mg/l", "g/l"],
    "pCO2": ["pco2", "partial pressure"],
    "pO2": ["po2", "partial pressure"]
}

# --- STANDARD BIO-FORMULAS (The Math Brain) ---
DEFAULT_EQUATIONS = {
    "Specific_Growth_Rate (mu)": {
        "formula": "={Dilution_Rate}", 
        "unit": "1/h", 
        "desc": "In steady-state chemostat, mu equals D."
    },
    "Dilution_Rate (D)": {
        "formula": "={Feed_Rate_L_h} / {Volume_L}",
        "unit": "1/h",
        "desc": "Flow per volume."
    },
    "Biomass_Yield (Yxs)": {
        "formula": "={VCD_Cells_mL} / {Glucose_Consumed_gL}",
        "unit": "Cells/g",
        "desc": "Cells produced per gram of substrate."
    },
    "Glucose_Consumption": {
        "formula": "={Feed_Glucose_Conc} - {Residual_Glucose}",
        "unit": "g/L",
        "desc": "Difference between inlet and outlet glucose."
    },
    "Specific_Prod_Rate (qP)": {
        "formula": "={Titer_mgL} * {Dilution_Rate} / {VCD_Cells_mL}",
        "unit": "mg/Cell/h",
        "desc": "Productivity per cell."
    },
    "Respiration_Quotient (RQ)": {
        "formula": "={CER} / {OUR}",
        "unit": "-",
        "desc": "Ratio of CO2 produced to O2 consumed."
    }
}

# --- 3. HELPER FUNCTIONS ---

def resolve_path(file_path):
    """
    Smart Path Finder: If the AI tries to use a Windows path or just a filename,
    this function looks inside 'temp_uploads' to find the real file.
    """
    # 1. Clean the input
    clean = file_path.strip('"').strip("'").replace('\\', '/')
    
    # 2. Check if it works as-is
    if os.path.exists(clean): 
        return clean
    
    # 3. Check inside the Streamlit upload folder
    filename = os.path.basename(clean)
    temp_path = os.path.join("temp_uploads", filename)
    
    if os.path.exists(temp_path): 
        print(f"[SYSTEM] 🔄 Redirected '{file_path}' to '{temp_path}'")
        return temp_path
        
    return None # File really doesn't exist

def load_knowledge():
    if os.path.exists(KNOWLEDGE_FILE):
        try:
            with open(KNOWLEDGE_FILE, 'r') as f: return json.load(f)
        except: pass
    # Now includes Equations!
    return {
        "ONLINE": DEFAULT_ONLINE, 
        "OFFLINE": DEFAULT_OFFLINE, 
        "EQUATIONS": DEFAULT_EQUATIONS
    }

def save_knowledge(knowledge_dict):
    try:
        with open(KNOWLEDGE_FILE, 'w') as f:
            json.dump(knowledge_dict, f, indent=4)
    except: pass

def smart_read_file(f_path):
    # USE THE RESOLVER
    real_path = resolve_path(f_path)
    if not real_path: return pd.DataFrame() # Return empty if not found
    
    try:
        if real_path.endswith('.xlsx'):
            xls = pd.ExcelFile(real_path)
            return pd.read_excel(xls, sheet_name=0)
        return pd.read_csv(real_path, sep=None, engine='python')
    except: return pd.DataFrame()

def extract_unit_from_header(header):
    match = re.search(r'[\[\(\{](.*?)[\]\)\}]|/\s*(.*)', str(header))
    return match.group(1) or match.group(2) if match else "Unknown"

def apply_schema_renaming(df, schema_dict):
    new_names = {}
    change_log = []
    for col in df.columns:
        col_lower = str(col).lower()
        unit = extract_unit_from_header(str(col))
        for standard_name, keywords in schema_dict.items():
            if any(k in col_lower for k in keywords):
                target = standard_name
                # Ensure unit is in the name if known and not already present
                if "[" not in target and unit != "Unknown":
                    target = f"{target} [{unit}]"
                
                if target in new_names.values(): target = f"{target}_{col}"
                new_names[col] = target
                change_log.append(f"Mapped '{col}' -> '{target}'")
                break
    if new_names: df = df.rename(columns=new_names)
    return df, change_log

async def auto_save_to_memory(callback_context):
    if hasattr(callback_context, '_invocation_context'):
        await callback_context._invocation_context.memory_service.add_session_to_memory(
            callback_context._invocation_context.session
        )

# --- 4. DATA TOOLS ---

def convert_pdf_to_excel(pdf_path: str, instruction: str = "Extract the main data table"):
    """
    SUPER-POWERED: Sends PDF to Gemini Vision (With Path Resolution & GC).
    """
    try:
        # 1. USE RESOLVER (Fixes "File not found" errors)
        # This is the helper function we added to find files in temp_uploads
        real_path = resolve_path(pdf_path)
        if not real_path: return f"Error: File not found. (I looked for '{pdf_path}')"
        
        print(f"[SYSTEM] 🧠 AI Vision Extraction for: {real_path}")
        print(f"[SYSTEM] 🗣️ Instruction: {instruction}")
        
        output = real_path.replace(".pdf", "_Converted.csv")
        
        # 2. Initialize Client
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GOOGLE_API_KEY)
        
        # 3. Read File (Load into RAM)
        with open(real_path, "rb") as f:
            pdf_bytes = f.read()
            
        prompt = f"""
        You are a Lab Data Assistant.
        USER INSTRUCTION: {instruction}
        
        TASK:
        1. Look at the PDF images provided.
        2. Execute the user instruction accurately.
        3. Output the result strictly as a raw CSV format.
        
        RULES:
        - Do NOT include markdown formatting (like ```csv).
        - Do NOT write introduction text. Just the data.
        - If headers are messy (e.g. "Conc.\\n(g/L)"), simplify them to "Conc_gL".
        """
        
        # 4. Call AI
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[types.Content(role="user", parts=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                types.Part.from_text(text=prompt)
            ])]
        )
        
        # 5. Clean & Save
        csv_content = response.text
        # Remove markdown if the AI adds it
        if "```" in csv_content:
            csv_content = csv_content.split("```csv")[-1].split("```")[0]
        
        with open(output, "w", encoding="utf-8") as f:
            f.write(csv_content.strip())
            
        # 6. MEMORY CLEANUP (Critical for Cloud Run)
        del pdf_bytes, response, csv_content
        gc.collect()
            
        return f"SUCCESS: AI converted PDF to {output}."

    except Exception as e: return f"Error with AI Vision: {e}"
  
def map_samples_to_time(data_file: str, key_file: str = None):
    """
    REAL LOGIC: Merges Analytical Data (HPLC/GC) with a Time Log (Key File).
    """
    try:
        # 1. Load Data (The measurements)
        print(f"[SYSTEM] 🗺️ Mapping: Data={data_file} | Key={key_file}")
        df_data = smart_read_file(data_file)
        if df_data.empty: return "Error: Data file is empty."

        # 2. If no Key File, check if Time exists inside the Data file
        # (Some modern HPLCs export time directly)
        if not key_file:
            time_col = next((c for c in df_data.columns if "time" in str(c).lower()), None)
            if time_col:
                return f"SUCCESS: File {data_file} already has a Time column ({time_col}). No mapping needed."
            return "STOP_AND_ASK: I have the data, but I need a 'Sample Log' (Key File) to link Sample IDs to Time. Please provide one."

        # 3. Load Key (The link between ID and Time)
        df_key = smart_read_file(key_file)
        
        # 4. Find Linking Columns (Smart Search)
        # We need a common column like "Sample Name", "Vial", "ID"
        # And a Time column in the Key
        key_time_col = next((c for c in df_key.columns if "time" in str(c).lower()), None)
        if not key_time_col: return f"Error: Key file {key_file} has no Time column."

        # Try to find a matching ID column in both
        common_cols = set(df_data.columns) & set(df_key.columns)
        link_col = next((c for c in common_cols if "sample" in str(c).lower() or "id" in str(c).lower() or "name" in str(c).lower()), None)
        
        if not link_col:
            # Fallback: Try to force join on the very first column if it looks like IDs
            link_col_data = df_data.columns[0]
            link_col_key = df_key.columns[0]
            # Rename to match
            df_key.rename(columns={link_col_key: link_col_data}, inplace=True)
            link_col = link_col_data

        # 5. MERGE
        # Left Join: Keep all measurements, attach time where IDs match
        merged = pd.merge(df_data, df_key[[link_col, key_time_col]], on=link_col, how='left')
        
        # 6. Save as Mapped File
        output = data_file.replace(".csv", "_Mapped.csv").replace(".xlsx", "_Mapped.csv")
        merged.to_csv(output, index=False)
        
        return f"SUCCESS: Mapped {data_file} using {key_file}. Saved to {output}. (Ready for Phase 3 Merge)."

    except Exception as e: return f"Error mapping samples: {e}"

def split_excel_sheets(file_path: str):
    try:
        clean_path = file_path.strip('"').replace('\\', '/')
        xls = pd.ExcelFile(clean_path)
        created = []
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            fname = f"{clean_path}_{sheet}.xlsx"
            df.to_excel(fname, index=False)
            created.append(fname)
        return f"Split into: {created}"
    except Exception as e: return f"Error: {e}"

def profile_file_content(file_path: str):
    try:
        df = smart_read_file(file_path)
        if df.empty: return "Empty file."
        desc = df.describe().to_string()
        return f"File Stats:\n{desc}"
    except Exception as e: return f"Error: {e}"

def align_and_merge_datasets(primary_file: str, secondary_file: str, output_filename: str = "Consolidated_Data.xlsx"):
    """
    Merges files with RAM OPTIMIZATION (Downcasting types + Aggressive GC).
    """
    try:
        knowledge = load_knowledge()
        
        # Helper to reduce memory usage
        def optimize_floats(df):
            floats = df.select_dtypes(include=['float64']).columns
            df[floats] = df[floats].astype('float32')
            return df

        # 1. Load & Optimize Primary
        print(f"[SYSTEM] 🧬 Loading Primary: {primary_file}")
        df1 = smart_read_file(primary_file)
        df1 = optimize_floats(df1)
        df1, _ = apply_schema_renaming(df1, knowledge["ONLINE"])
        
        # 2. Load & Optimize Secondary
        print(f"[SYSTEM] 💉 Loading Secondary: {secondary_file}")
        df2 = smart_read_file(secondary_file)
        df2 = optimize_floats(df2)
        df2, _ = apply_schema_renaming(df2, knowledge["ONLINE"])
        
        # 3. Identify Time
        t1 = next((c for c in df1.columns if "time" in str(c).lower()), None)
        t2 = next((c for c in df2.columns if "time" in str(c).lower()), None)

        if not t1: return f"Error: Primary file {primary_file} has no Time column."
        if not t2: return f"Error: Secondary file {secondary_file} has no Time column."

        # 4. Sort (Required)
        df1 = df1.sort_values(t1)
        df2 = df2.sort_values(t2)
        
        # 5. Merge (Nearest match)
        print("[SYSTEM] ⚗️ Merging dataframes...")
        merged = pd.merge_asof(df1, df2, left_on=t1, right_on=t2, direction='nearest', tolerance=pd.Timedelta("10min"))
        
        # 6. Save
        print(f"[SYSTEM] 💾 Saving to {output_filename}...")
        merged.to_excel(output_filename, index=False)
        
        # 7. AGGRESSIVE MEMORY CLEANUP (The Missing Part)
        del df1, df2, merged  # Delete variables
        gc.collect()          # Force RAM release immediately
        
        return f"SUCCESS: Merged {secondary_file} into {primary_file}. Saved to '{output_filename}'"

    except Exception as e: return f"Error merging: {e}"

def append_offline_sheet(source_file: str, output_filename: str):
    try:
        df = smart_read_file(source_file)
        if not os.path.exists(output_filename):
            df.to_excel(output_filename, index=False)
            return f"Created new file {output_filename}"
        
        with pd.ExcelWriter(output_filename, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            sheet_name = os.path.basename(source_file)[:30] # Excel limit 31 chars
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        return f"SUCCESS: Appended {sheet_name}"
    except Exception as e: return f"Error: {e}"

def teach_bioprocess_knowledge(standard_name, raw_name, category="ONLINE"):
    """Teaches the AI a new synonym and saves it."""
    try:
        knowledge = load_knowledge()
        if category not in knowledge: return "Error: Category must be ONLINE or OFFLINE."
        if standard_name not in knowledge[category]: knowledge[category][standard_name] = []
        
        if raw_name.lower() not in knowledge[category][standard_name]:
            knowledge[category][standard_name].append(raw_name.lower())
            save_knowledge(knowledge)
            return f"SUCCESS: Learned that '{raw_name}' is '{standard_name}'."
        return f"INFO: I already knew '{raw_name}'."
    except Exception as e: return f"Error: {e}"

def create_formula_reference(filename: str, context: str, equations_dict: str, units_dict: str):
    """
    Creates a professional Formula Reference Document (.docx) with tables.
    Accepts dictionaries as strings or objects.
    """
    try:
        if not filename.endswith(".docx"): filename += ".docx"
        
        doc = Document()
        doc.add_heading('Bioprocess Formula Reference', 0)
        doc.add_paragraph(context)
        
        # Helper to parse input safely
        def safe_load(input_data):
            if isinstance(input_data, dict): return input_data
            try: return json.loads(input_data)
            except: return None

        # 1. Equations Section
        doc.add_heading('1. Key Equations', level=1)
        eq_data = safe_load(equations_dict)
        
        if eq_data:
            table = doc.add_table(rows=1, cols=2)
            table.style = 'Table Grid'
            hdr = table.rows[0].cells
            hdr[0].text = 'Parameter'
            hdr[1].text = 'Equation'
            for name, formula in eq_data.items():
                row = table.add_row().cells
                row[0].text = str(name)
                row[1].text = str(formula)
        else:
            doc.add_paragraph(str(equations_dict))

        # 2. Units Section
        doc.add_heading('2. Unit Definitions', level=1)
        unit_data = safe_load(units_dict)
        
        if unit_data:
            table = doc.add_table(rows=1, cols=2)
            table.style = 'Table Grid'
            hdr = table.rows[0].cells
            hdr[0].text = 'Variable'
            hdr[1].text = 'Unit'
            for var, unit in unit_data.items():
                row = table.add_row().cells
                row[0].text = str(var)
                row[1].text = str(unit)
        else:
            doc.add_paragraph(str(units_dict))
            
        doc.save(filename)
        return f"SUCCESS: Created Formula Reference at '{filename}'."
    except Exception as e: return f"Error creating doc: {e}"

# --- 5. REPORTING & ANALYSIS TOOLS ---

def add_calculated_column(file_path: str, new_col_name: str, formula_template: str):
    """Creates a new column in Excel using a formula."""
    try:
        clean_path = file_path.strip('"').strip("'").replace('\\', '/')
        wb = load_workbook(clean_path)
        ws = wb.active 
        col_map = {}
        headers = [cell.value for cell in ws[1]]
        for idx, h in enumerate(headers, 1):
            if h: col_map[str(h).strip()] = get_column_letter(idx)

        new_col_idx = ws.max_column + 1
        ws.cell(row=1, column=new_col_idx, value=new_col_name)
        
        import re
        ingredients = re.findall(r'\{(.*?)\}', formula_template)
        for row in range(2, ws.max_row + 1):
            row_formula = formula_template
            valid = True
            for ing in ingredients:
                if ing in col_map:
                    row_formula = row_formula.replace(f"{{{ing}}}", f"{col_map[ing]}{row}")
                else: valid = False
            if valid: ws.cell(row=row, column=new_col_idx, value=row_formula)
        wb.save(clean_path)
        return f"SUCCESS: Added column '{new_col_name}' to {clean_path}."
    except Exception as e: return f"Error: {e}"

def add_bioprocess_analysis(file_path: str, graph_column: str = "Dissolved Oxygen"):
    """Adds a line graph to the Excel file."""
    try:
        clean_path = file_path.strip('"').replace('\\', '/')
        wb = load_workbook(clean_path)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        try:
            time_idx = next(i for i, h in enumerate(headers) if h and "Time" in str(h)) + 1
            data_idx = next(i for i, h in enumerate(headers) if h and graph_column in str(h)) + 1
        except: return f"Error: Could not find Time or {graph_column} columns."

        chart = LineChart()
        chart.title = graph_column
        chart.x_axis.title = "Time"
        data = Reference(ws, min_col=data_idx, min_row=1, max_row=ws.max_row)
        cats = Reference(ws, min_col=time_idx, min_row=2, max_row=ws.max_row)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        ws.add_chart(chart, "E5")
        wb.save(clean_path)
        return f"SUCCESS: Graph added to {clean_path}"
    except Exception as e: return f"Error: {e}"

def structure_excel_report(file_path: str):
    """Formats Excel into tabs."""
    try:
        clean_path = file_path.strip('"').replace('\\', '/')
        df = smart_read_file(clean_path)
        output = clean_path.replace(".xlsx", "_Formatted.xlsx")
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Main_Data', index=False)
        return f"SUCCESS: Formatted report: {output}"
    except Exception as e: return f"Error: {e}"

def create_word_report(summary: str, filename: str = "Report.docx"):
    try:
        doc = Document()
        doc.add_heading('Bioprocess Report', 0)
        doc.add_paragraph(summary)
        doc.save(filename)
        return f"Report saved to {filename}"
    except Exception as e: return f"Error: {e}"

# --- 6. SUB-AGENT DEFINITIONS ---

data_extractor_agent = LlmAgent(
    name="Data_Extractor_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Maps files intelligently, handles PDFs, and merges data.",
    instruction="""
    You are a Smart Data Engineer. You execute the "Clean Slate" protocol.
    
    ### 🗣️ CRITICAL SAFETY RULE:
    **You MUST output a thought/sentence before calling ANY tool.**
    * BAD: (Calls tool silently) -> CRASH.
    * GOOD: "I see a PDF. I will convert it now." -> (Calls tool).

    ### 🧠 INTELLIGENCE:
    - You use `bioprocess_knowledge.json` automatically.
    - **TEACHING MODE:** If you see an unmapped column (e.g., "T_P1"), use `teach_bioprocess_knowledge`.

    ### 🛠️ EXECUTION FLOW:
    
    1. **PHASE 1: CONVERT (PDFs)**
       - If PDF? -> Say "Converting [filename]..." then use `convert_pdf_to_excel`.
       - Result is a `.csv`. Use this for next steps.

    2. **PHASE 2: CHECK TIME**
       - If a file has no "Time" column (Offline data), Say "Mapping samples..." then use `map_samples_to_time`.

    3. **PHASE 3: BUILD THE CONSOLIDATED FILE**
       - **First Merge:** Say "Initializing Consolidated Data..." then pick the Main Sensor File as `primary` and Offgas as `secondary`.
         - Output MUST be `output_filename="Consolidated_Data.xlsx"`.
       - **Next Merges:** Say "Merging [file]..." then use `align_and_merge_datasets`:
         - `primary_file`: "Consolidated_Data.xlsx".
         - `secondary_file`: The next new file.
         - `output_filename`: "Consolidated_Data.xlsx" (Overwrite it).

    4. **PHASE 4: APPEND**
       - For single data points, Say "Appending offline data..." then use `append_offline_sheet`.
    
    5. **REPORT:** Confirm the final filename ("Consolidated_Data.xlsx") and columns.
    """,
    tools=[
        convert_pdf_to_excel, 
        map_samples_to_time, 
        profile_file_content, 
        split_excel_sheets, 
        align_and_merge_datasets, 
        append_offline_sheet, 
        teach_bioprocess_knowledge
    ], 
)

research_agent = LlmAgent(
    name="Research_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Finds scientific info.",
    instruction="""
    You are a Scientific Researcher.
    
    ### 🧠 KNOWLEDGE SOURCE:
    1. **Check Local Knowledge First:** Look at `DEFAULT_EQUATIONS` in the system prompt logic (if available).
    2. **Google Search:** If the user asks for a formula NOT in your defaults, use `Google Search`.
    
    ### 📝 TASKS:
    1. **Draft Formula Sheet:**
       - When asked, compile a list of formulas.
       - Use `create_formula_reference(filename, context, equations_dict, units_dict)`.
       - **Format:** `equations_dict` MUST be a JSON string like '{"Yield": "={A}/{B}"}'.
    """,
    tools=[google_search, create_formula_reference],
)

# --- UPGRADED MATHEMATICAL AGENTS ---

formula_agent = LlmAgent(
    name="Excel_Formula_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Adds dynamic Excel formulas.",
    instruction="""
    You are an Excel Specialist. Your job is to inject **Calculations** into the spreadsheet.
    
    ### 🗣️ SAFETY: Speak before acting. (Prevent Crash)
    ### ⚠️ PRECISION: You CANNOT assume column names. Check first.
    
    ### ⚙️ EXECUTION RULES:
    1. **CHECK:** Say "Inspecting headers..." -> Call `profile_file_content`.
    2. **APPLY:** Say "Applying Excel formula for [Parameter]..." -> Call `add_calculated_column`.
       - **CRITICAL:** You must write **EXCEL SYNTAX** (e.g., `={Gluc_gL} / {Biomass_gL}`).
       - Use the EXACT column names found in Step 1.
    """,
    tools=[add_calculated_column, profile_file_content],
)

excel_analyst_agent = LlmAgent(
    name="Excel_Analyst_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Creates scientific graphs in Excel.",
    instruction="""
    You are a Data Visualization Expert.
    
    ### 🗣️ SAFETY: Speak before acting.
    
    ### ⚙️ EXECUTION RULES:
    1. **CHECK:** Say "Reading file structure..." -> Call `profile_file_content`.
    2. **GRAPH:** Say "Creating graph for [Column]..." -> Call `add_bioprocess_analysis`.
       - Only graph columns that actually exist (check headers first).
    """,
    tools=[add_bioprocess_analysis, profile_file_content], 
)

formatter_agent = LlmAgent(
    name="Report_Formatter_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Formats Excel tabs.",
    instruction="Use `structure_excel_report` to organize the file.",
    tools=[structure_excel_report],
)

report_writer_agent = LlmAgent(
    name="Word_Report_Agent",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Writes Word reports.",
    instruction="Summarize findings into a Word document.",
    tools=[create_word_report]
)

# --- 7. ROOT AGENT ---

Bioprocess_agent = LlmAgent(
    name="Bioprocess_Manager",
    model=Gemini(model="gemini-2.5-flash-lite", api_key=GOOGLE_API_KEY, retry_options=retry_config),
    description="Manager of the bioprocess pipeline.",
    instruction="""
    You are the Bioprocess Project Manager. You orchestrate the data lifecycle from Raw Files to Final Report.

    ### 🧠 KNOWLEDGE & INTERNET ACCESS (Use Anytime):
    You have a `Research_Agent` who can access Google Search.
    * **WHEN TO USE:** If you need a formula, a constant (e.g., "Molecular Weight of Glucose"), or need to understand a specific bioprocess term.
    * **RULE:** Do not guess scientific facts. Ask the Researcher.

    ### 🗣️ TRANSPARENCY RULE:
    Always explain your plan before acting.
    * "I see PDFs. I will convert them first."
    * "I need the molecular weight of Ethanol to calculate the yield. Asking the Researcher..."

    ### 🔄 THE LIFECYCLE (Your Roadmap):
    You can start at any step depending on the user's input, but logically follow this flow:

    **STEP 1: DATA ENGINEERING (Extract & Merge)**
    * **Goal:** Create a single, clean "Consolidated_Data.xlsx".
    * **Logic:**
        * If PDFs? -> Send to `Data_Extractor` (`convert_pdf_to_excel`).
        * If Multiple Files? -> Send to `Data_Extractor` (Merge backbone first, then append satellites).
    * **CRITICAL:** Stop and ask the user to confirm the "Consolidated_Data.xlsx" and check the units before moving to Step 2.

    **STEP 2: THEORETICAL FRAMEWORK (Formula Collection)**
    * **Goal:** Create a "Formula_Reference.docx" based on available columns.
    * **Action:**
        * Look at the columns in Consolidated_Data.
        * Ask `Research_Agent` for relevant bioprocess formulas (e.g., if you see Glucose/Biomass, look for Yields).
        * Command `Research_Agent` (or Reporter) to create a "Formula Collection Document" with a Unit Table.
    * **Stop:** Ask user to confirm the formulas.

    **STEP 3: CALCULATION (Excel Implementation)**
    * **Goal:** Apply the confirmed formulas into the Excel file.
    * **Action:** Send instructions to `Excel_Formula_Agent` to add columns (e.g. `add_calculated_column`).

    **STEP 4: VISUALIZATION (Graphing)**
    * **Goal:** Create trends.
    * **Action:** Send instructions to `Excel_Analyst_Agent` to generate graphs inside the Excel.

    **STEP 5: INTERPRETATION (Final Reporting)**
    * **Goal:** Scientific Conclusion.
    * **Action:**
        * Ask the user for a template or specific questions.
        * Send data summary to `Word_Report_Agent` to write the "Final_Bioprocess_Report.docx".

    **ALWAYS** pass the filename (e.g., "Consolidated_Data.xlsx") explicitly to the next agent.
    """,
    tools=[
        preload_memory, 
        AgentTool(agent=data_extractor_agent), 
        AgentTool(agent=research_agent), 
        AgentTool(agent=excel_analyst_agent), 
        AgentTool(agent=formula_agent), 
        AgentTool(agent=formatter_agent), 
        AgentTool(agent=report_writer_agent)
    ],
    after_agent_callback=auto_save_to_memory
)

# --- 7. THE MISSING PIECE: THE RUNNER ---
# This wrapper handles user_id and session_id correctly
auto_runner = Runner(
    agent=Bioprocess_agent,
    app_name=APP_NAME,
    session_service=session_service,
    memory_service=memory_service,
)