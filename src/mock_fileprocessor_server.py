import os
import csv
import io
import json
import tempfile
from decimal import Decimal, InvalidOperation
from datetime import datetime
from google.cloud import storage
from mcp.server.fastmcp import FastMCP

# Initialize the MCP Server
mcp = FastMCP("FileProcessor-Agent")

BUCKET_NAME = os.getenv("BUCKET_NAME", "day-aiagents-2026-doc-ingest")
# Initialize storage client globally, but gracefully handle missing credentials if needed
try:
    storage_client = storage.Client()
except Exception:
    storage_client = None

def extract_text_from_file(filepath: str) -> str:
    """Extracts text from various document types (txt, pdf, docx, xlsx, csv)."""
    if not os.path.exists(filepath):
        return None

    ext = filepath.lower().split('.')[-1]
    
    try:
        if ext == 'pdf':
            import fitz  # PyMuPDF
            text = ""
            with fitz.open(filepath) as doc:
                for page in doc:
                    text += page.get_text() + "\n"
            return text
            
        elif ext == 'docx':
            import docx
            doc = docx.Document(filepath)
            return "\n".join([p.text for p in doc.paragraphs])
            
        elif ext in ['xlsx', 'xls']:
            import pandas as pd
            df = pd.read_excel(filepath)
            return df.to_string(index=False)
            
        elif ext == 'csv':
            import pandas as pd
            df = pd.read_csv(filepath)
            return df.to_string(index=False)
            
        else:
            # Fallback to plain text decoding
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        return f"Error extracting text from {filepath}: {str(e)}"

def get_latest_feed_from_gcs(platform_name: str) -> str:
    """Finds the most appropriate file for a platform in Google Cloud Storage"""
    if not storage_client:
        return "Google Cloud Storage client not initialized."
        
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs()
    
    target_blobs = []
    for blob in blobs:
        if platform_name.lower() in blob.name.lower():
            target_blobs.append(blob)
            
    if not target_blobs:
        return f"No updates found for {platform_name} today."
        
    all_texts = []
    for target_blob in target_blobs:
        # Download to temp file
        ext = target_blob.name.lower().split('.')[-1] if '.' in target_blob.name else 'txt'
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp_file:
            temp_filepath = temp_file.name
            
        target_blob.download_to_filename(temp_filepath)
            
        try:
            text = extract_text_from_file(temp_filepath)
            if text:
                all_texts.append(f"--- Content from {target_blob.name} ---\n{text}")
        finally:
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
        
    return "\n\n".join(all_texts)

@mcp.tool()
def get_daily_social_summary() -> str:
    """Fetches the latest updates from LinkedIn and WhatsApp by reading uploaded mock documents from Cloud Storage."""
    payload = {
        "status": "success",
        "source_platforms": ["LinkedIn", "WhatsApp"],
        "data": {
            "linkedin_raw": get_latest_feed_from_gcs("linkedin"),
            "whatsapp_raw": get_latest_feed_from_gcs("whatsapp")
        }
    }
    return json.dumps(payload, indent=2)

@mcp.tool()
def query_specific_document(filename: str) -> str:
    """Fetches text content from a specific uploaded document in Google Cloud Storage."""
    if not storage_client:
        return "Google Cloud Storage client not initialized."
        
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    if not blob.exists():
        return f"File {filename} not found in Google Cloud Storage."
        
    ext = filename.lower().split('.')[-1] if '.' in filename else 'txt'
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp_file:
        temp_filepath = temp_file.name
        
    blob.download_to_filename(temp_filepath)
        
    try:
        text = extract_text_from_file(temp_filepath)
    finally:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        
    return text

def to_jde_julian(date_str: str) -> int:
    """Transforms standard date text into an E1 6-digit Julian Integer (1YYDDD)."""
    try:
        if not date_str:
            return 0
            
        date_str = date_str.strip()
        # Remove quotes if they somehow remain
        if date_str.startswith('"') and date_str.endswith('"'):
            date_str = date_str[1:-1]
            
        formats = ["%Y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"]
        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
                
        if dt is None:
            return 0
            
        year = dt.year
        day_of_year = dt.timetuple().tm_yday
        jde_year = year - 1900
        return int(f"{jde_year}{day_of_year:03d}")
    except Exception:
        return 0

def to_jde_numeric(amount_val) -> int:
    """Eliminates literal decimal points to scale currency values into JDE Math Numerics."""
    try:
        val = Decimal(str(amount_val))
        return int(round(val * 100))
    except (InvalidOperation, ValueError, TypeError):
        return 0

@mcp.tool(
    name="generate_jde_f03b13z1_csv",
    description=(
        "Converts a raw array of check, credit card, and debit card transactions "
        "into a 17-column CSV payload mapped specifically for the JDE F03B13Z1 table. "
        "Automates Julian date conversions, decimal adjustments, and payment instrument routing. "
        "IMPORTANT: By default, DO NOT output any explanations of the key conversions applied "
        "unless the user explicitly asks for them. If the user asks for an Excel export or a "
        "tabular format, you MUST output the resulting JDE structure as a Markdown Table. "
        "Otherwise, output the raw CSV payload inside a code block."
    )
)
def generate_jde_f03b13z1_csv(transactions_json: str) -> str:
    """
    Antigravity Native Tool Interface Core.
    Accepts incoming transactional streams and generates the target JDE structure.
    """
    try:
        transactions = json.loads(transactions_json)
    except Exception as e:
        return f"Error parsing input JSON payload: {str(e)}"
        
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    
    headers = [
"RUEDUS", "RUEDBT", "RUEDTN", "RUEDLN", "RUCKNU", "RUICUT", "RUCKAM", "RUAG",
"RUCBNK", "RUTNST", "RUGMFD", "RUVR01", "RUVR02", "RURMK", "RUDOCM", "RUAMTS",
"RUDMTJ"
    ]
    
    writer.writerow(headers)
    
    for tx in transactions:
        ruckam = to_jde_numeric(tx.get("payment_amount", 0))
        ruvr02 = str(tx.get("deposit_id", ""))[:25]
        rudocm = str(tx.get("payment_id", ""))[:8]
        ruamts = to_jde_numeric(tx.get("total_payment_amount", 0))
        rudmtj = to_jde_julian(str(tx.get("payment_date", "")))
        
        is_card = tx.get("payment_instrument") in ["X", "D", "W"]
        rutnst = "" if is_card else str(tx.get("bank_transit_routing", ""))[:20]
        rucbnk = "" if is_card else str(tx.get("bank_account_number", ""))[:20]
        
        ruag = to_jde_numeric(tx.get("amount_applied", 0))
        rurmk = str(tx.get("credit_card_number", ""))[:30]
        ruvr01 = str(tx.get("authorization_number", ""))[:25]
        rugmfd = str(tx.get("generic_matching_field", ""))[:50]
        
        ruedtn = str(tx.get("source_system_doc_number", ""))[:20]
        ruuser = str(tx.get("user_id_or_session", ""))[:10]
        ruedus = str(tx.get("user_id_or_session", ""))[:10]
        ruicut = "9B" 
        ruedbt = str(tx.get("bank_lockbox_number", ""))[:15]
        rzrmk = str(tx.get("customer_name", ""))[:40] 
        
        writer.writerow([
            ruckam, ruvr02, rudocm, ruamts, 
            rudmtj, rutnst, rucbnk, ruag, rurmk, 
            ruvr01, rugmfd, ruedtn, ruuser, ruedus, 
            ruicut, ruedbt, rzrmk
        ])
        
    return output.getvalue()

@mcp.tool(
    name="process_dynamic_csv_to_jde",
    description=(
        "A high-performance parser that converts raw bank CSV content directly to a 17-column "
        "JDE F03B13Z1 CSV using a dynamic field mapping. Use this tool instead of 'generate_jde_f03b13z1_csv' "
        "when processing large Lockbox CSV files to prevent timeouts. "
        "The mapping_json must map JDE columns to their source columns in the CSV. "
        "Supported JDE columns: RUEDUS, RUEDBT, RUEDTN, RUEDLN, RUCKNU, RUICUT, RUCKAM, RUAG, "
        "RUCBNK, RUTNST, RUGMFD, RUVR01, RUVR02, RURMK, RUDOCM, RUAMTS, RUDMTJ. "
        "Mapping object properties for each column: "
        " - 'source_column': Exact header name from the CSV "
        " - 'transform': 'mult_100', 'julian', or 'none' "
        " - 'constant': Hardcoded value (ignores source_column if provided) "
        "IMPORTANT: Output the resulting JDE structure as a Markdown Table if tabular format is requested. "
        "Otherwise, output the raw CSV payload inside a code block."
    )
)
def process_dynamic_csv_to_jde(csv_content: str, mapping_json: str) -> str:
    """
    Dynamically maps raw CSV rows into the JDE payload instantly.
    """
    try:
        mapping = json.loads(mapping_json)
    except Exception as e:
        return f"Error parsing mapping JSON: {e}"

    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    
    headers = [
        "RUEDUS", "RUEDBT", "RUEDTN", "RUEDLN", "RUCKNU", "RUICUT", "RUCKAM", "RUAG",
        "RUCBNK", "RUTNST", "RUGMFD", "RUVR01", "RUVR02", "RURMK", "RUDOCM", "RUAMTS",
        "RUDMTJ"
    ]
    
    writer.writerow(headers)
    
    reader = csv.DictReader(io.StringIO(csv_content))
    if not reader.fieldnames:
        return "Error: Empty or invalid CSV content."
    
    for row in reader:
        out_row = []
        for h in headers:
            col_map = mapping.get(h, {})
            
            val = ""
            if "constant" in col_map:
                val = col_map["constant"]
            elif "source_column" in col_map:
                src_col = col_map["source_column"]
                val = row.get(src_col, "")
            else:
                val = col_map.get("default", "")
                
            transform = col_map.get("transform", "none")
            
            if transform == "mult_100":
                val = to_jde_numeric(val)
            elif transform == "julian":
                val = to_jde_julian(str(val))
            else:
                val = str(val)
                
            out_row.append(val)
            
        writer.writerow(out_row)
        
    return output.getvalue()

if __name__ == "__main__":
    mcp.run()
