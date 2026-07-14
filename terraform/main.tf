terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --- Cloud Storage (Ingestion) ---
resource "google_storage_bucket" "document_bucket" {
  name          = var.bucket_name
  location      = var.region
  force_destroy = true
  uniform_bucket_level_access = true
}

# Pub/Sub system service account needs publisher role to trigger Eventarc
data "google_storage_project_service_account" "gcs_account" {}

resource "google_project_iam_member" "gcs_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"
}

# --- BigQuery (Storage) ---
resource "google_bigquery_dataset" "doc_dataset" {
  dataset_id                  = var.dataset_id
  friendly_name               = "Document Metadata Dataset"
  description                 = "Dataset for storing extracted document metadata"
  location                    = var.region
}

resource "google_bigquery_table" "metadata_table" {
  dataset_id          = google_bigquery_dataset.doc_dataset.dataset_id
  table_id            = var.table_id
  deletion_protection = false

  schema = <<EOF
[
  {
    "name": "filename",
    "type": "STRING",
    "mode": "REQUIRED"
  },
  {
    "name": "file_uri",
    "type": "STRING",
    "mode": "REQUIRED"
  },
  {
    "name": "upload_time",
    "type": "TIMESTAMP",
    "mode": "REQUIRED"
  },
  {
    "name": "file_type",
    "type": "STRING",
    "mode": "NULLABLE"
  },
  {
    "name": "tags",
    "type": "STRING",
    "mode": "REPEATED"
  },
  {
    "name": "metadata_json",
    "type": "JSON",
    "mode": "NULLABLE"
  },
  {
    "name": "session_id",
    "type": "STRING",
    "mode": "NULLABLE"
  }
]
EOF
}

# --- Cloud Run (Processor) ---
# Service Account for Cloud Run
resource "google_service_account" "cloudrun_sa" {
  account_id   = "document-processor-sa"
  display_name = "Cloud Run Document Processor SA"
}

# Grant Cloud Run SA access to read GCS and write to BigQuery
resource "google_project_iam_member" "cloudrun_gcs_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

resource "google_project_iam_member" "cloudrun_bq_writer" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

resource "google_project_iam_member" "cloudrun_bq_jobuser" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

resource "google_project_iam_member" "cloudrun_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

resource "google_cloud_run_v2_service" "processor_service" {
  name     = var.service_name
  location = var.region
  
  # For internal triggers, we could restrict ingress, but for Eventarc sometimes internal+LB is needed.
  # "INGRESS_TRAFFIC_INTERNAL_ONLY" is safest, but "INGRESS_TRAFFIC_ALL" is easier if we don't have a VPC.
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloudrun_sa.email
    containers {
      # Dummy image for initial deploy, real image will be deployed later via gcloud run deploy
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GEMINI_API_KEY"
        value = var.gemini_api_key
      }
      env {
        name  = "DATASET_ID"
        value = google_bigquery_dataset.doc_dataset.dataset_id
      }
      env {
        name  = "TABLE_ID"
        value = google_bigquery_table.metadata_table.table_id
      }
    }
  }

  # Ignore lifecycle changes to image so gcloud run deploy doesn't get reverted by terraform
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }
}

# Allow Eventarc to invoke Cloud Run
resource "google_cloud_run_v2_service_iam_member" "eventarc_invoker" {
  project  = google_cloud_run_v2_service.processor_service.project
  location = google_cloud_run_v2_service.processor_service.location
  name     = google_cloud_run_v2_service.processor_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.eventarc_sa.email}"
}

# --- Eventarc (Trigger) ---
resource "google_service_account" "eventarc_sa" {
  account_id   = "eventarc-trigger-sa"
  display_name = "Eventarc Trigger Service Account"
}

resource "google_project_iam_member" "eventarc_event_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.eventarc_sa.email}"
}

resource "google_eventarc_trigger" "gcs_trigger" {
  name     = "gcs-upload-trigger"
  location = var.region
  service_account = google_service_account.eventarc_sa.email

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }
  
  matching_criteria {
    attribute = "bucket"
    value     = google_storage_bucket.document_bucket.name
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.processor_service.name
      region  = var.region
    }
  }

  depends_on = [
    google_project_iam_member.gcs_pubsub_publisher
  ]
}

# --- Cloud Scheduler (Cleanup) ---
resource "google_cloud_scheduler_job" "cleanup_job" {
  name             = "docuflow-daily-cleanup"
  description      = "Deletes files older than 7 days"
  schedule         = "0 2 * * *"
  time_zone        = "America/New_York"
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.processor_service.uri}/admin/cleanup"

    oidc_token {
      service_account_email = google_service_account.cloudrun_sa.email
    }
  }
}
