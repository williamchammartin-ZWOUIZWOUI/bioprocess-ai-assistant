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
* **Accuracy:** Eliminates human copy-paste errors when digitizing PDF reports.

---

## II. 🧠 Agent Architecture

This project utilizes a hierarchical multi-agent system built on the **Google Agent Development Kit (ADK)**. A root **Bioprocess Manager** orchestrates specialized sub-agents to handle specific scientific tasks.

### Key Concepts Implemented (3+ Concepts Verified)

| Concept | Implementation in Code |
| :--- | :--- |
| **1. Multi-Agent System** | The system coordinates **6 specialized agents**: `Data_Extractor`, `Research`, `Excel_Formula`, `Excel_Analyst`, `Report_Formatter`, and `Word_Report_Agent`. |
| **2. Custom Tools** | The `Data_Extractor_Agent` utilizes a custom **`convert_pdf_to_excel`** tool that leverages Gemini's Vision capabilities to scrape tabular data from PDF lab reports. |
| **3. Sessions & Memory** | The app uses `InMemorySessionService` to maintain context across the workflow, allowing the agent to "remember" the Consolidated Data file path across different user prompts. |

---

## III. ⚙️ The Workflow (5-Step Pipeline)

The agent follows a logical scientific workflow:

1.  **Ingestion & Cleaning:**
    * **Agent:** `Data_Extractor_Agent`
    * **Task:** Intelligent merging of sensor data (CSV) and analytical reports (PDF). It resolves timestamp mismatches between offline samples and online trends.
2.  **Theoretical Framework:**
    * **Agent:** `Research_Agent`
    * **Task:** Uses **Google Search** to find relevant bioprocess constants (e.g., molecular weights) and drafts a `Formula_Reference.docx`.
3.  **Transparent Calculation (The "Enterprise" Feature):**
    * **Agent:** `Excel_Formula_Agent`
    * **Task:** Instead of calculating in Python, it uses the `add_calculated_column` tool to **write Excel formulas directly into the cells**. This ensures the final file is dynamic and auditable by the scientist.
4.  **Visualization:**
    * **Agent:** `Excel_Analyst_Agent`
    * **Task:** Generates standard bioprocess plots (e.g., Time vs. Dissolved Oxygen) inside the Excel workbook.
5.  **Reporting:**
    * **Agent:** `Word_Report_Agent`
    * **Task:** Synthesizes findings into a professional `Report.docx`.

---

## IV. 🛠️ Installation & Usage

### Prerequisites
* Python 3.10+
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
3.  **Set your API Key:**
    *(Security Note: Never hardcode this key!)*
    ```bash
    export GOOGLE_API_KEY="your_actual_api_key_here"
    ```
4.  **Run the App:**
    ```bash
    streamlit run app.py
    ```

### ☁️ Cloud Deployment (Google Cloud Run)
This project is containerized for enterprise deployment.

1.  **Build & Deploy:**
    The repository includes a `Dockerfile` and a deployment script.
    ```bash
    # Ensure your Google Cloud SDK is authenticated
    ./bash deploy.sh
    ```
    *Note: The deployment script securely passes the API key as an environment variable.*

---

## V. 📂 File Structure

* `app.py`: The Streamlit frontend interface.
* `backend_agent.py`: The core ADK agent logic, tool definitions, and pipeline orchestration.
* `bioprocess_knowledge.json`: A domain-specific dictionary mapping raw sensor names to standard variables.
* `Dockerfile`: Configuration for containerizing the application.
* `requirements.txt`: Project dependencies.

---