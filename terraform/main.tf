provider "google" {
  project = var.project_id
  region  = var.region
}

# Create Cloud Storage Bucket for Media Files
resource "google_storage_bucket" "media_files" {
  name           = "${var.project_id}-media-files"
  location       = var.region
  force_destroy  = true
}

# Create Cloud Storage Bucket for Static files
resource "google_storage_bucket" "staticfiles" {
  name           = "${var.project_id}-staticfiles"
  location       = var.region
  force_destroy  = true
}

# Cloud SQL Instance
resource "google_sql_database_instance" "postgres_instance" {
  name             = "pg-instance"
  database_version = "POSTGRES_17"
  region           = var.region

  settings {
    tier = "db-f1-micro"
    edition = "ENTERPRISE"
  }
}

# Create service account
resource "google_service_account" "django_sa" {
  account_id   = "django-cloudrun-sa"
  display_name = "Django Cloud Run Service Account"
}

# Create Artifact Repository to store the application image
resource "google_artifact_registry_repository" "main" {
  format        = "DOCKER"
  location      = var.region
  project       = var.project_id
  repository_id = "django-app"
}

# Cloud SQL User & DB
resource "google_sql_user" "postgres_user" {
  name     = var.db_user
  instance = google_sql_database_instance.postgres_instance.name
  password = var.db_password
}

resource "google_sql_database" "app_db" {
  name     = var.db_name
  instance = google_sql_database_instance.postgres_instance.name
}

# Create local variables
locals {
  service_account = "serviceAccount:${google_service_account.django_sa.email}"
  repository_id   = google_artifact_registry_repository.main.repository_id
  ar_repository   = "${var.region}-docker.pkg.dev/${var.project_id}/${local.repository_id}"
  image           = "${local.ar_repository}/${var.service_name}"
}

# Secret Manager: DB Password
resource "google_secret_manager_secret" "db_password" {
  secret_id = "django-db-password"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password_version" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data_wo = var.db_password
}

# Create a random string to use as the Django secret key
resource "random_password" "django_secret_key" {
  special = false
  length  = 50
}

# Create application settings data with terraform template and save in secret
resource "google_secret_manager_secret" "application_settings" {
  secret_id = "application_settings"
  replication {
    auto {}
  }
}

# Replace the Terraform template variables and save the rendered content as a secret
resource "google_secret_manager_secret_version" "application_settings" {
  secret = google_secret_manager_secret.application_settings.id

  secret_data = templatefile("${path.module}/templates/application_settings.tftpl", {
      staticfiles_bucket = google_storage_bucket.staticfiles.name
      mediafiles_bucket = google_storage_bucket.media_files.name
      secret_key         = random_password.django_secret_key.result
      db_user            = google_sql_user.postgres_user.name
      db_password           = google_sql_user.postgres_user.password
      db_instance_name   = google_sql_database_instance.postgres_instance.name
      db_instance_project   = google_sql_database_instance.postgres_instance.project
      db_instance_region   = google_sql_database_instance.postgres_instance.region
      db_name            = google_sql_database.app_db.name
  })
}

# Generate a random password for the superuser
resource "random_password" "superuser_password" {
  length  = 32
  special = false
}

# Save the superuser password as a secret
resource "google_secret_manager_secret" "superuser_password" {
  secret_id = "superuser_password"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "superuser_password" {
  secret      = google_secret_manager_secret.superuser_password.id
  secret_data = random_password.superuser_password.result
}

# Create google credential json file and store in secrets
resource "google_service_account_key" "django_key" {
  service_account_id = google_service_account.django_sa.name
  keepers = {
    last_rotation = timestamp()
  }
  private_key_type = "TYPE_GOOGLE_CREDENTIALS_FILE"
}

resource "google_secret_manager_secret" "django_key" {
  secret_id = "django-sa-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "django_key" {
  secret      = google_secret_manager_secret.django_key.id
  secret_data_wo = base64decode(google_service_account_key.django_key.private_key)
}

# Grant all permissions

# Secret permissions
# Grant Cloud Run access to Secret
resource "google_secret_manager_secret_iam_binding" "cloudrun_secret_access" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  members    = [local.service_account]
}

# Grant the Cloud Run service account access to the application settings secret
resource "google_secret_manager_secret_iam_binding" "application_settings" {
  secret_id = google_secret_manager_secret.application_settings.id
  role      = "roles/secretmanager.secretAccessor"
  members   = [local.service_account]
}

# Grant the Cloud Run service account access to the superuser password secret
resource "google_secret_manager_secret_iam_binding" "superuser_password" {
  secret_id = google_secret_manager_secret.superuser_password.id
  role      = "roles/secretmanager.secretAccessor"
  members   = [local.service_account]
}

# Grant the Cloud Run service account access to the superuser password secret
resource "google_secret_manager_secret_iam_binding" "django_key" {
  secret_id = google_secret_manager_secret.django_key.id
  role      = "roles/secretmanager.secretAccessor"
  members   = [local.service_account]
}

# Service permissions
# Permissions for Storage Buckets
resource "google_storage_bucket_iam_binding" "media_files" {
  bucket = google_storage_bucket.media_files.name
  role   = "roles/storage.admin"
  members = [local.service_account]
}

resource "google_storage_bucket_iam_binding" "staticfiles" {
  bucket = google_storage_bucket.staticfiles.name
  role   = "roles/storage.admin"
  members = [local.service_account]
}

# Permissions for Cloud Run to access Cloud SQL and Run
resource "google_project_iam_member" "service_roles" {
  for_each = toset([
    "cloudsql.client",
    "run.viewer",
  ])
  project = var.project_id
  role    = "roles/${each.key}"
  member  = local.service_account
}


# Build the application image that the Cloud Run service and jobs will use
resource "terraform_data" "cbstg_app" {

  triggers_replace = {
    app_code = sha256(join("", [for f in fileset("${path.module}/../cbstg", "**/*.py"): filesha256("${path.root}/../cbstg/${f}")]))
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../cbstg"
    command     = "gcloud builds submit --pack image=${local.image} ."
  }

  depends_on = [
    google_artifact_registry_repository.main,
  ]
}


# Create the migrate_collectstatic Cloud Run job
resource "google_cloud_run_v2_job" "migrate_collectstatic" {
  name     = "migrate-collectstatic"
  location = var.region

  template {
    template {
      service_account = google_service_account.django_sa.email

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres_instance.connection_name]
        }
      }

      containers {
        image   = local.image
        command = ["migrate_collectstatic"]

        env {
          name = "APPLICATION_SETTINGS"
          value_source {
            secret_key_ref {
              version = google_secret_manager_secret_version.application_settings.version
              secret  = google_secret_manager_secret_version.application_settings.secret
            }
          }
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
  }
  depends_on = [
    terraform_data.cbstg_app,
  ]
}

# Create the create_superuser Cloud Run job
resource "google_cloud_run_v2_job" "create_superuser" {
  name     = "create-superuser"
  location = var.region

  template {
    template {
      service_account = google_service_account.django_sa.email

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres_instance.connection_name]
        }
      }
      containers {
        image   = local.image
        command = ["create_superuser"]
        env {
          name = "APPLICATION_SETTINGS"
          value_source {
            secret_key_ref {
              version = google_secret_manager_secret_version.application_settings.version
              secret  = google_secret_manager_secret_version.application_settings.secret
            }
          }
        }
        env {
          name = "DJANGO_SUPERUSER_PASSWORD"
          value_source {
            secret_key_ref {
              version = google_secret_manager_secret_version.superuser_password.version
              secret  = google_secret_manager_secret_version.superuser_password.secret
            }
          }
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }
  }
  depends_on = [
    terraform_data.cbstg_app
  ]
}

# Run the migrate_collectstatic the Cloud Run job
resource "terraform_data" "execute_migrate_collectstatic" {
  provisioner "local-exec" {
    command = "gcloud run jobs execute migrate-collectstatic --region ${var.region} --wait"
  }
  depends_on = [
    google_cloud_run_v2_job.migrate_collectstatic,
  ]
}

# Run the create_superuser the Cloud Run job
resource "terraform_data" "execute_create_superuser" {
  provisioner "local-exec" {
    command = "gcloud run jobs execute create-superuser --region ${var.region} --wait"
  }
  depends_on = [
    google_cloud_run_v2_job.create_superuser,
  ]
}

# Create and deploy the Cloud Run service
resource "google_cloud_run_v2_service" "app" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  template {
    containers {
      image = local.image
      env {
        name  = "SERVICE_NAME"
        value = var.service_name
      }
      env {
        name = "APPLICATION_SETTINGS"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret_version.application_settings.secret
            version = google_secret_manager_secret_version.application_settings.version
          }
        }
      }
      env {
        name  = "GOOGLE_APPLICATION_CREDENTIALS"
        value = "/secrets/django-sa-key.json"
      }
      volume_mounts {
        name       = "secret-vol"
        mount_path = "/secrets"
      }
    }
    volumes {
      name = "secret-vol"
      secret {
        secret = google_secret_manager_secret_version.django_key.secret
        items {
          path    = "django-sa-key.json"
          version = "latest"
        }
      }
    }
    service_account = google_service_account.django_sa.email
    annotations = {
      "run.googleapis.com/cloudsql-instances" = google_sql_database_instance.postgres_instance.connection_name
      "run.googleapis.com/client-name"        = "terraform"
    }
  }
  depends_on = [
    terraform_data.execute_migrate_collectstatic,
    terraform_data.execute_create_superuser,
  ]
}


# Grant permission to unauthenticated users to invoke the Cloud Run service
data "google_iam_policy" "noauth" {
  binding {
    role    = "roles/run.invoker"
    members = ["allUsers"]
  }
}

resource "google_cloud_run_service_iam_policy" "noauth" {
  location = google_cloud_run_v2_service.app.location
  project  = google_cloud_run_v2_service.app.project
  service  = google_cloud_run_v2_service.app.name
  policy_data = data.google_iam_policy.noauth.policy_data
}
