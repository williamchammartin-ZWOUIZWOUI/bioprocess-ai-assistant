# 🧬 Bioprocess AI Lab Assistant

**Capstone Project: Agents Intensive with Google ADK**
* **Name:** William Chammartin
* **Track:** Enterprise Agents
* **Submission Date:** December 1, 2025

---

## I. 💡 Problem Statement (The Pitch)

In the biopharmaceutical industry, **data integrity and auditability** are critical. Scientists currently face a major bottleneck:
1.  **Fragmented Data:** Merging time-series data from disparate sources (online sensors, offgas analyzers, offline HPLC/GC PDFs) is manual and error-prone.
2.  **The "Black Box" Problem:** Most automation tools calculate results in the background and output a static number. **Scientists cannot accept these results** because they cannot see *how* the calculation was performed. If the math isn't visible, it isn't auditable.

**The Solution:**
The **Bioprocess AI Assistant** is an Enterprise-grade tool that automates the data lifecycle while preserving full scientific transparency. It doesn't just "do the math"—it **writes the Excel formulas for you**.

**Value Proposition:**
* **Audit-Ready:** By injecting native Excel formulas (e.g., `={VCD}/{Glucose}`), the agent allows scientists to validate and tweak calculations directly in the spreadsheet.
* **Efficiency:** Reduces data processing time from hours to minutes.
* **Cost-Effective:** Optimized to run on **Gemini 2.5 Flash Lite** for high speed and minimal API costs.
* **Accuracy:** Eliminates human copy-paste errors when digitizing PDF reports.

---

## II. 🧠 Agent Architecture

This project utilizes a hierarchical multi-agent system built on the **Google Agent Development Kit (ADK)**. A root **Bioprocess_Manager** orchestrates 6 specialized sub-agents to handle specific scientific tasks.

### Key Concepts Implemented

| Concept | Implementation in Code |
| :--- | :--- |
| **1. Multi-Agent System** | The system coordinates **6 specialized agents**: `Data_Wrangler`, `Excel_Architect`, `Research_Agent`, `Excel_Formula`, `Excel_Analyst`, and `Word_Report_Agent`. |
| **2. Custom Tools** | The `Data_Wrangler` utilizes a custom **`convert_pdf_to_excel`** tool that leverages Gemini's Vision capabilities to scrape tabular data from PDF lab reports. |
| **3. Sessions & Memory** | The app uses `InMemorySessionService` to maintain context across the workflow, allowing the agent to "remember" file paths across different user prompts. |

---

## III. ⚙️ The Workflow (6-Phase Pipeline)

The `Bioprocess_Manager` follows a logical scientific workflow to ensure data integrity:

1.  **Phase 1: Extraction & Conversion**
    * **Agent:** `Data_Wrangler_Agent`
    * **Task:** Uses Gemini Vision to convert PDF lab reports into raw CSV data.
2.  **Phase 2: Cleaning**
    * **Agent:** `Data_Wrangler_Agent`
    * **Task:** Cleans the data (removes zeroes, aligns timestamps) using Python.
3.  **Phase 3: Merging**
    * **Agent:** `Data_Wrangler_Agent`
    * **Task:** Merges offline sample data with online sensor trends based on timestamps.
4.  **Phase 4: Assembly (The Architect)**
    * **Agent:** `Excel_Architect_Agent`
    * **Task:** Physically constructs the `Consolidated_Data.xlsx` file, creating specific sheets for "Online_Data" and "Offline_Data".
5.  **Phase 5: Analysis (Transparent Calculation)**
    * **Agent:** `Research_Agent` & `Excel_Formula_Agent`
    * **Task:** First, the Researcher finds constants (e.g., Molecular Weights). Then, the Formula Agent uses `add_calculated_column` to **write Excel formulas directly into the cells**.
    * **Visualization:** The `Excel_Analyst_Agent` generates native Excel charts (e.g., Time vs. Dissolved Oxygen).
6.  **Phase 6: Reporting**
    * **Agent:** `Word_Report_Agent`
    * **Task:** Synthesizes findings into a professional `Report.docx`.

---

## IV. 🛠️ Installation & Usage

### Prerequisites
* Python 3.11+
* A Google Cloud Project with Vertex AI API enabled.
* A Gemini API Key.

### Local Setup
1.  **Clone the repository:**
    ```bash
    git clone [INSERT YOUR REPO URL HERE]
    cd bioprocess-ai-assistant
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Set your API Key (Securely):**
    Create a file named `.env` in the root folder and add your key:
    ```ini
    GOOGLE_API_KEY="your_actual_api_key_here"
    GOOGLE_CLOUD_PROJECT="adept-might-479811-q5"
    ```
    *(Note: The `.gitignore` file prevents this secret key from being uploaded to GitHub.)*

4.  **Run the App:**
    ```bash
    streamlit run app.py
    ```

### ☁️ Cloud Deployment (Google Cloud Run)
This project is containerized for enterprise deployment.

1.  **Make the script executable:**
    ```bash
    chmod +x deploy.sh
    ```
2.  **Deploy Securely:**
    Pass your API key as a variable when running the script. **Do not** write your key inside the script file.
    ```bash
    API_KEY="your_actual_api_key_here" ./deploy.sh
    ```

---

## V. 📂 File Structure

* `app.py`: The Streamlit frontend interface with async event loop handling.
* `backend_agent.py`: The core ADK agent logic, tool definitions, and pipeline orchestration.
* `deploy.sh`: Script to build and deploy the Docker container to Google Cloud Run.
* `Dockerfile`: Configuration for containerizing the application (Python 3.11-slim).
* `requirements.txt`: Project dependencies.
* `.env`: (Local only) Stores your API keys securely.


---
