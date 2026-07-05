# DocuFlow AI: Serverless Document Processing Pipeline

DocuFlow AI is an advanced, serverless, agentic application that allows you to upload documents, securely store them, and instantly query their contents using a chat-based UI powered by Gemini 3.5 Flash and the Model Context Protocol (MCP).

## Features

- **Document Ingestion**: Upload up to 15 files at once (.pdf, .docx, .png, .xlsx, .csv) via a modern, glassmorphism UI.
- **Agentic Q&A**: Ask complex questions about the documents you've uploaded. The AI uses function calling (MCP) to selectively read the exact files needed to answer your question.
- **Dynamic Skill-Loading Engine**: An extensible `SKILL.md` architecture allows you to dynamically onboard new processing rules (e.g., new Bank Lockbox formats) without modifying Python code. The engine automatically scans the `src/skills/` directory and injects the rules at runtime.
- **High-Performance Data Parsing**: Utilizes a highly optimized Python MCP tool (`process_dynamic_csv_to_jde`) to instantly parse and map large CSV datasets to standard formats (like JDE F03B13Z1) in milliseconds, preventing AI timeouts.
- **Export Capabilities**: Export tabular AI answers directly to Excel or PDF with a single click.
- **Session Management**: Return to the app with your unique Session ID to instantly restore your previously uploaded documents and context.
- **Fully Serverless Architecture**: Built with Flask and deployed effortlessly on Google Cloud Run. Data is securely managed through Google Cloud Storage and logged in BigQuery.

## Technology Stack

- **Frontend**: HTML5, Vanilla JavaScript, CSS3 (Custom Glassmorphism UI)
- **Backend**: Python 3.10+, Flask Application
- **AI / LLM**: Google Gemini 3.5 Flash via `google-genai`
- **Agentic Protocol**: Model Context Protocol (MCP) using `mcp` library (FastMCP)
- **Cloud Infrastructure**: Google Cloud Run, Cloud Storage (GCS), BigQuery, Eventarc

## Project Structure

```text
├── src/
│   ├── static/
│   │   ├── app.js             # Frontend logic (file uploading, chat interface, UI interactions)
│   │   └── index.css          # Custom styling (glass panels, animations, responsive grid)
│   ├── templates/
│   │   └── index.html         # Main dashboard interface
│   ├── skills/                # Dynamic SKILL.md instruction files mapped by use case
│   ├── main.py                # Flask server, routing, dynamic skills loader, and Gemini loop
│   ├── processor.py           # Document upload handling and Cloud Storage/BigQuery integration
│   ├── exporters.py           # Logic for converting Markdown tables to PDF and Excel formats
│   ├── mock_fileprocessor_server.py # Local MCP server for high-performance JDE CSV processing
│   ├── requirements.txt       # Python dependencies
│   └── Dockerfile             # Container definition for Cloud Run deployment
```

## How It Works (The Agentic Loop)

When you ask a question:
1. **Request**: The frontend sends your question and the list of selected files to the Flask backend.
2. **Context**: The backend initializes a local MCP server (`mock_fileprocessor_server.py`) and dynamically reads all loaded `SKILL.md` rules.
3. **Reasoning**: Gemini 3.5 Flash reviews your question, the dynamic skills, and the available MCP tools.
4. **Action**: Gemini executes function calls (like fetching a document or transforming a CSV). By leveraging the dynamic `process_dynamic_csv_to_jde` tool, it hands off heavy parsing tasks directly to Python for instant execution.
5. **Response**: Gemini formulates the final answer. If it contains tabular data, export buttons automatically appear!

## Running Locally

1. Install dependencies:
   ```bash
   pip install -r src/requirements.txt
   ```
2. Set your Google credentials (required for GCS/BigQuery) and Gemini API key:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
   export GEMINI_API_KEY="your_api_key_here"
   ```
3. Run the Flask application:
   ```bash
   python src/main.py
   ```
4. Open your browser and navigate to `http://127.0.0.1:8080`.

## Deploying to Cloud Run

Deploying to Google Cloud is fully handled by `gcloud`. Ensure you are authenticated and have set your project, then run:

```bash
gcloud run deploy doc-processor-service --source src/ --region us-central1 --allow-unauthenticated
```
