import os
import tempfile
import logging
import json
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from google.cloud import storage, bigquery
import fitz  # PyMuPDF
from docx import Document
import pandas as pd
from PIL import Image

PROJECT_ID = os.environ.get("PROJECT_ID", "day-aiagents-2026")
DATASET_ID = os.environ.get("DATASET_ID", "doc_processing_metadata")
TABLE_ID = os.environ.get("TABLE_ID", "documents")

storage_client = storage.Client(project=PROJECT_ID)
bq_client = bigquery.Client(project=PROJECT_ID)

def extract_pdf_metadata(file_path):
    tags = ["pdf"]
    metadata = {}
    try:
        doc = fitz.open(file_path)
        metadata["pages"] = doc.page_count
        metadata["title"] = doc.metadata.get("title", "")
        doc.close()
    except Exception as e:
        logging.error(f"PDF extraction error: {e}")
    return tags, metadata

def extract_docx_metadata(file_path):
    tags = ["docx", "document"]
    metadata = {}
    try:
        doc = Document(file_path)
        metadata["paragraphs"] = len(doc.paragraphs)
        metadata["core_properties"] = {
            "author": doc.core_properties.author,
            "title": doc.core_properties.title
        }
    except Exception as e:
        logging.error(f"DOCX extraction error: {e}")
    return tags, metadata

def extract_excel_metadata(file_path):
    tags = ["excel", "spreadsheet"]
    metadata = {}
    try:
        xl = pd.ExcelFile(file_path)
        metadata["sheet_names"] = xl.sheet_names
        metadata["num_sheets"] = len(xl.sheet_names)
    except Exception as e:
        logging.error(f"Excel extraction error: {e}")
    return tags, metadata

def extract_image_metadata(file_path):
    tags = ["image"]
    metadata = {}
    try:
        with Image.open(file_path) as img:
            metadata["format"] = img.format
            metadata["size"] = list(img.size)  # width, height
            metadata["mode"] = img.mode
            if img.format:
                tags.append(img.format.lower())
    except Exception as e:
        logging.error(f"Image extraction error: {e}")
    return tags, metadata

def process_document(bucket_name, file_name):
    _, ext = os.path.splitext(file_name)
    ext = ext.lower()
    
    # Download file to temp storage
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
        blob.download_to_filename(temp_file.name)
        temp_path = temp_file.name

    tags = []
    metadata = {}
    
    try:
        if ext == ".pdf":
            tags, metadata = extract_pdf_metadata(temp_path)
        elif ext in [".docx"]:
            tags, metadata = extract_docx_metadata(temp_path)
        elif ext in [".xlsx", ".xls"]:
            tags, metadata = extract_excel_metadata(temp_path)
        elif ext in [".png", ".jpeg", ".jpg"]:
            tags, metadata = extract_image_metadata(temp_path)
        else:
            tags = ["unknown"]
            metadata = {"extension": ext}

        file_uri = f"gs://{bucket_name}/{file_name}"
        
        # Read session_id from custom metadata
        blob.reload() # Ensure metadata is loaded
        session_id = blob.metadata.get('session_id') if blob.metadata else None
        
        row = {
            "filename": file_name,
            "file_uri": file_uri,
            "upload_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "file_type": ext.lstrip('.'),
            "tags": tags,
            "metadata_json": metadata,
            "session_id": session_id
        }

        # Load into BigQuery (bypasses streaming buffer, allowing immediate deletion)
        table_ref = bq_client.dataset(DATASET_ID).table(TABLE_ID)
        table = bq_client.get_table(table_ref)
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            schema=table.schema
        )
        job = bq_client.load_table_from_json([row], table_ref, job_config=job_config)
        job.result() # Wait for the job to complete
            
        logging.info(f"Successfully processed and recorded metadata for {file_name}")

    finally:
        os.remove(temp_path)
