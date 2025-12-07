# 🧪 How to Test the Bioprocess AI Assistant

This repository includes a `Messy files to work with` folder containing real-world "messy" bioprocess data (PDF reports, raw sensor CSVs, and Excel maps). Follow this guide to see the AI clean, merge, and analyze this data automatically, even if it contains irrelevant data and samples.

## 📂 The Scenario
You are a student who has just finished a chemostat experiment for a Lab Practical (TP). You have data scattered across different formats:
* **PDFs:** Lab reports from HPLC and GC (Sugar, Acetate, Ethanol).
* **CSVs/Excel:** Online sensor data (pH, DO) and Off-gas analyzer data.
* **Sample Map:** An Excel file linking sample times to sample IDs.

**Your Goal:** Merge all these files into a single, audit-ready Excel report with calculated yields and charts.

---

## 🚀 Step-by-Step Test Instructions

### Step 1: Launch the App
Run the Streamlit app locally:
```bash
streamlit run app.py