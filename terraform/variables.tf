variable "project_id" {
  description = "The GCP Project ID"
  type        = string
}

variable "region" {
  description = "The GCP region to deploy resources to"
  type        = string
  default     = "us-central1"
}

variable "bucket_name" {
  description = "Name of the GCS bucket for document ingestion"
  type        = string
}

variable "dataset_id" {
  description = "BigQuery Dataset ID"
  type        = string
  default     = "doc_processing_metadata"
}

variable "table_id" {
  description = "BigQuery Table ID"
  type        = string
  default     = "documents"
}

variable "service_name" {
  description = "Cloud Run Service Name"
  type        = string
  default     = "doc-processor-service"
}

variable "gemini_api_key" {
  description = "The Gemini API Key"
  type        = string
  sensitive   = true
}
