variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "europe-central2"
}

variable "db_user" {
  description = "Database username"
  type        = string
  default     = "django"
}

variable "db_password" {
  description = "Database user password"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Name of the database"
  type        = string
  default     = "django_db"
}

variable "service_name" {
  type        = string
  description = "Name of Cloud Run service"
}