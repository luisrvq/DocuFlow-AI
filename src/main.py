import os
import logging
import random
import mimetypes
from dotenv import load_dotenv
load_dotenv()
import asyncio
from flask import Flask, request, render_template, jsonify, send_file
from google.cloud import storage, bigquery

from processor import process_document
from exporters import ExcelExporter, PdfExporter

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_ID = os.environ.get("PROJECT_ID", "day-aiagents-2026")
DATASET_ID = os.environ.get("DATASET_ID", "doc_processing_metadata")
TABLE_ID = os.environ.get("TABLE_ID", "documents")
# Hardcode the bucket since we know it, or read from env
BUCKET_NAME = f"{PROJECT_ID}-doc-ingest" if PROJECT_ID else os.environ.get("BUCKET_NAME", "day-aiagents-2026-doc-ingest")
REGION = os.environ.get("REGION", "us-central1")

from google import genai
from google.genai import types

# Configure GenAI
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

storage_client = storage.Client(project=PROJECT_ID) if PROJECT_ID else storage.Client()
bq_client = bigquery.Client(project=PROJECT_ID) if PROJECT_ID else bigquery.Client()

@app.route("/", methods=["GET"])
def index():
    """Render the main UI."""
    documents = []
    session_id = request.args.get('session_id')
    
    if session_id:
        try:
            query = f"SELECT filename, file_type, CAST(upload_time AS STRING) as upload_time, tags FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE session_id = @session_id ORDER BY upload_time DESC"
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("session_id", "STRING", session_id)
                ]
            )
            query_job = bq_client.query(query, job_config=job_config)
            results = query_job.result()
            for row in results:
                doc = {
                    "filename": row.filename,
                    "file_type": row.file_type.upper() if row.file_type else "UNKNOWN",
                    "upload_time": row.upload_time[:19].replace("T", " "), # Format nicely
                    "tags": ", ".join(row.tags) if row.tags else ""
                }
                documents.append(doc)
        except Exception as e:
            logging.error(f"Error querying BigQuery: {e}")

    return render_template("index.html", documents=documents)

@app.route("/", methods=["POST"])
def receive_event():
    """Receive an Eventarc trigger (CloudEvents)."""
    ce_type = request.headers.get("ce-type")
    
    if ce_type != "google.cloud.storage.object.v1.finalized":
        logging.warning(f"Ignored event type: {ce_type}")
        return "Ignored", 204

    event_data = request.get_json()
    if not event_data:
        return "Bad Request", 400

    bucket_name = event_data.get("bucket")
    file_name = event_data.get("name")
    
    if not bucket_name or not file_name:
        return "Bad Request", 400

    logging.info(f"Processing gs://{bucket_name}/{file_name}")

    try:
        process_document(bucket_name, file_name)
        return "OK", 200
    except Exception as e:
        logging.error(f"Error processing {file_name}: {e}")
        return str(e), 500

#-----------------------------------------------------------------------------#
# Upload Route                                                                #
#   - Receiving uploaded files                                                #
#   - Processing document metadata                                            #
#   - Storing files in Google Cloud Storage                                   #
#   - Logging metadata for retrieval                                          #
#-----------------------------------------------------------------------------#
@app.route("/upload", methods=["POST"])
def upload_file():
    """Handle UI file uploads."""
    session_id = request.headers.get("X-Session-ID")
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        for file in files:
            blob = bucket.blob(file.filename)
            blob.metadata = {'session_id': session_id} if session_id else {}
            blob.upload_from_file(file.stream, content_type=file.content_type)
        return jsonify({"message": "Files uploaded successfully"}), 200
    except Exception as e:
        logging.error(f"Upload error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/delete/<filename>", methods=["DELETE"])
def delete_file(filename):
    """Delete file from GCS and BQ."""
    try:
        # 1. Delete from GCS
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        if blob.exists():
            blob.delete()
        
        # 2. Delete from BQ
        session_id = request.headers.get("X-Session-ID")
        query = f"DELETE FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE filename = @filename AND session_id = @session_id"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("filename", "STRING", filename),
                bigquery.ScalarQueryParameter("session_id", "STRING", session_id)
            ]
        )
        query_job = bq_client.query(query, job_config=job_config)
        query_job.result()
        
        return jsonify({"message": "Deleted successfully"}), 200
    except Exception as e:
        logging.error(f"Delete error: {e}")
        return jsonify({"error": str(e)}), 500

#-----------------------------------------------------------------------------#
# Ask Route                                                                   #
#   - Receives the user's question                                            #
#   - Initializes an MCP Client Session                                       #
#   - Loads available skills dynamically                                      #
#   - Retrieves available tools from the MCP server                           #
#   - Sends context and tool definitions to Gemini                            #
#   - Executes tool calls when requested                                      #
#   - Returns a formatted response                                            #
#-----------------------------------------------------------------------------#
@app.route("/ask", methods=["POST"])
def ask_question():
    """Endpoint for Q&A using Gemini AI Studio."""
    data = request.get_json()
    question = data.get("question", "")
    filenames = data.get("filenames", [])
    
    if not question:
        return jsonify({"error": "Question is required"}), 400

    try:
        parts = []
        bucket = storage_client.bucket(BUCKET_NAME)
        
        for fn in filenames:
            blob = bucket.blob(fn)
            file_bytes = blob.download_as_bytes()
            ext = fn.lower().split('.')[-1] if '.' in fn else ''
            
            if ext in ['png', 'jpeg', 'jpg']:
                mime = f"image/{'jpeg' if ext == 'jpg' else ext}"
                parts.append(types.Part.from_bytes(data=file_bytes, mime_type=mime))
            elif ext == 'pdf':
                parts.append(types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"))
            elif ext in ['xlsx', 'xls', 'csv']:
                import pandas as pd
                import io
                if ext == 'csv':
                    df = pd.read_csv(io.BytesIO(file_bytes))
                else:
                    df = pd.read_excel(io.BytesIO(file_bytes))
                csv_data = df.to_csv(index=False)
                parts.append(f"Contents of {fn}:\n{csv_data}")
            elif ext == 'docx':
                import docx
                import io
                doc = docx.Document(io.BytesIO(file_bytes))
                text = "\n".join([p.text for p in doc.paragraphs])
                parts.append(f"Contents of {fn}:\n{text}")
            else:
                # Attempt to decode as text
                try:
                    parts.append(f"Contents of {fn}:\n{file_bytes.decode('utf-8')}")
                except:
                    logging.warning(f"Unsupported file type could not be decoded: {fn}")
            
        parts.append(question)
        
        if not client:
            return jsonify({"error": "Gemini API Client not initialized"}), 500
            
        async def run_mcp_agent(question_text, document_parts, gemini_client):
            import sys
            # Pointing to the local mock_fileprocessor_server.py using the exact same python environment
            server_params = StdioServerParameters(command=sys.executable, args=["mock_fileprocessor_server.py"])
            
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    mcp_tools = await session.list_tools()
                    
                    gemini_tools = []
                    for t in mcp_tools.tools:
                        properties = {}
                        required = t.inputSchema.get("required", []) if t.inputSchema else []
                        
                        if t.inputSchema and "properties" in t.inputSchema:
                            for prop_name, prop_schema in t.inputSchema["properties"].items():
                                prop_type = types.Type.STRING if prop_schema.get("type") == "string" else types.Type.ANY
                                properties[prop_name] = types.Schema(
                                    type=prop_type,
                                    description=prop_schema.get("description", "")
                                )
                        
                        parameters = None
                        if properties:
                            parameters = types.Schema(
                                type=types.Type.OBJECT,
                                properties=properties,
                                required=required
                            )
                            
                        gemini_tools.append(types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters=parameters
                        ))
                    
                    tool_config = types.Tool(function_declarations=gemini_tools) if gemini_tools else None
                    
                    config_kwargs = {}
                    if tool_config:
                        config_kwargs["tools"] = [tool_config]
                    
                    # Dynamic Skill Loading
                    skills_text = []
                    skills_dir = os.path.join(os.path.dirname(__file__), "skills")
                    if os.path.exists(skills_dir):
                        for root, _, files in os.walk(skills_dir):
                            for file in files:
                                if file.endswith(".md"):
                                    try:
                                        with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                                            skills_text.append(f.read())
                                    except Exception as e:
                                        logging.error(f"Error reading skill {file}: {e}")
                    
                    if skills_text:
                        config_kwargs["system_instruction"] = "\n\n---\nSKILLS LOADED:\n\n" + "\n\n".join(skills_text)

                    chat_config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
                    
                    chat = gemini_client.chats.create(model="gemini-3.5-flash", config=chat_config)
                    
                    response = chat.send_message(document_parts + [question_text])
                    
                    iteration_count = 0
                    while response.function_calls and iteration_count < 5:
                        iteration_count += 1
                        tool_responses = []
                        for call in response.function_calls:
                            try:
                                mcp_res = await session.call_tool(call.name, call.args)
                                content_str = "\n".join([c.text for c in mcp_res.content if c.type == "text"])
                            except Exception as e:
                                content_str = f"Error calling tool: {e}"
                                
                            tool_responses.append(types.Part.from_function_response(
                                name=call.name,
                                response={"result": content_str}
                            ))
                        response = chat.send_message(tool_responses)
                        
                    if iteration_count >= 5:
                        return "I could not find the answer after multiple attempts. Please refine your question or select relevant documents."
                        
                    try:
                        return response.text
                    except ValueError:
                        return "I'm sorry, I cannot fulfill that request or I lack the necessary context."

        answer = asyncio.run(run_mcp_agent(question, parts[:-1], client))
        return jsonify({"answer": answer}), 200
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        if hasattr(e, 'exceptions'):
            tb += "\\nSub-exceptions:\\n"
            for idx, sub_e in enumerate(e.exceptions):
                tb += f"[{idx}] {type(sub_e).__name__}: {str(sub_e)}\\n"
        return jsonify({"error": tb}), 500

#-----------------------------------------------------------------------------#
# Export Route                                                                #
#   - Formatting AI-generated results                                         #
#   - Generating CSV, XLSX, or PDF outputs                                    #
#   - Returning downloadable files to the user                                #
#-----------------------------------------------------------------------------#
@app.route("/export", methods=["POST"])
def export_data():
    try:
        req = request.get_json()
        content = req.get("content", "")
        fmt = req.get("format", "excel")
        
        if fmt == "excel":
            exporter = ExcelExporter()
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ext = "xlsx"
        elif fmt == "pdf":
            exporter = PdfExporter()
            mimetype = "application/pdf"
            ext = "pdf"
        else:
            return jsonify({"error": "Unsupported format"}), 400
            
        file_stream = exporter.export(content)
        return send_file(
            file_stream,
            mimetype=mimetype,
            as_attachment=True,
            download_name=f"export.{ext}"
        )
    except Exception as e:
        logging.error(f"Export error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/admin/cleanup", methods=["POST"])
def cleanup_old_files():
    """Delete files and DB records older than 7 days."""
    try:
        # 1. Query BigQuery for old files
        query = f"SELECT filename FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE upload_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) AND session_id IS NOT NULL"
        query_job = bq_client.query(query)
        results = query_job.result()
        
        # 2. Delete from GCS
        bucket = storage_client.bucket(BUCKET_NAME)
        for row in results:
            blob = bucket.blob(row.filename)
            if blob.exists():
                blob.delete()
                
        # 3. Delete from BigQuery
        delete_query = f"DELETE FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE upload_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) AND session_id IS NOT NULL"
        bq_client.query(delete_query).result()
        
        return "Cleanup successful", 200
    except Exception as e:
        logging.error(f"Cleanup error: {e}")
        return str(e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
