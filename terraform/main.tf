provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloud Storage Bucket
resource "google_storage_bucket" "media_files" {
  name           = "${var.project_id}-media-files"
  location       = var.region
  force_destroy  = true
}

# Cloud Storage Bucket Static files
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

resource "google_service_account" "django_sa" {
  account_id   = "django-cloudrun-sa"
  display_name = "Django Cloud Run Service Account"
}

# Create a Artifact Repository to store the application image
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

resource "google_secret_manager_secret" "database_url" {
  secret_id = "django-database-url"
  replication {
    auto {}
  }
}

# IAM Permissions for Cloud Run to access Cloud SQL & Storage
resource "google_project_iam_member" "cloudsql_access" {
  project = var.project_id
  role   = "roles/cloudsql.client"
  member = "serviceAccount:${google_service_account.django_sa.email}"
}

resource "google_project_iam_member" "storage_access" {
  project = var.project_id
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.django_sa.email}"
}

# IAM: Grant Cloud Run access to Secret
resource "google_secret_manager_secret_iam_member" "cloudrun_secret_access" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.django_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "cloudrun_database_url_access" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.django_sa.email}"
}

locals {
  service_account = "serviceAccount:${google_service_account.django_sa.email}"
  repository_id   = google_artifact_registry_repository.main.repository_id
  ar_repository   = "${var.region}-docker.pkg.dev/${var.project_id}/${local.repository_id}"
  image           = "${local.ar_repository}/${var.service_name}"
}

resource "google_project_iam_member" "service_roles" {
  for_each = toset([
    "cloudsql.client",
    "run.viewer",
  ])
  project = var.project_id
  role    = "roles/${each.key}"
  member  = local.service_account
}

# Create a random string to use as the Django secret key
resource "random_password" "django_secret_key" {
  special = false
  length  = 50
}

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

# Grant the Cloud Run service account access to the application settings secret
resource "google_secret_manager_secret_iam_binding" "application_settings" {
  secret_id = google_secret_manager_secret.application_settings.id
  role      = "roles/secretmanager.secretAccessor"
  members   = [local.service_account]
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

# Grant the Cloud Run service account access to the superuser password secret
resource "google_secret_manager_secret_iam_binding" "superuser_password" {
  secret_id = google_secret_manager_secret.superuser_password.id
  role      = "roles/secretmanager.secretAccessor"
  members   = [local.service_account]
}

# Build the application image that the Cloud Run service and jobs will use
resource "terraform_data" "bootstrap" {
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
    terraform_data.bootstrap,
  ]
}


# Setup enviroment
resource "google_cloud_run_v2_job" "setup_enviroment" {
  name     = "setup-enviroment"
  location = var.region

  template {
    template {
      service_account = google_service_account.django_sa.email

      containers {
        image   = local.image
        command = ["setup_enviroment"]

      }
    }
  }

  depends_on = [
    terraform_data.bootstrap,
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
    terraform_data.bootstrap
  ]
}

# Run the setup_enviroment the Cloud Run job
resource "terraform_data" "execute_setup_enviroment" {
  provisioner "local-exec" {
    command = "gcloud run jobs execute setup-enviroment --region ${var.region} --wait"
  }

  depends_on = [
    google_cloud_run_v2_job.setup_enviroment,
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
resource "google_cloud_run_service" "app" {
  name                       = var.service_name
  location                   = var.region
  autogenerate_revision_name = true

  lifecycle {
    replace_triggered_by = [terraform_data.bootstrap]
  }

  template {
    spec {
      service_account_name = google_service_account.django_sa.email
      containers {
        image = local.image

        env {
          name  = "SERVICE_NAME"
          value = var.service_name
        }

        env {
          name = "APPLICATION_SETTINGS"
          value_from {
            secret_key_ref {
              key  = google_secret_manager_secret_version.application_settings.version
              name = google_secret_manager_secret.application_settings.secret_id
            }
          }
        }
      }
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/maxScale"      = "1"
        "run.googleapis.com/cloudsql-instances" = google_sql_database_instance.postgres_instance.connection_name
        "run.googleapis.com/client-name"        = "terraform"
      }
    }


  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [
    terraform_data.execute_setup_enviroment,
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
  location = google_cloud_run_service.app.location
  project  = google_cloud_run_service.app.project
  service  = google_cloud_run_service.app.name

  policy_data = data.google_iam_policy.noauth.policy_data
}
