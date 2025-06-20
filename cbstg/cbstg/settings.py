import io
from urllib.parse import urlparse

import environ
import google.auth
import requests
from google.cloud.run_v2.services.services.client import ServicesClient
from google.oauth2 import service_account

from .basesettings import *
import local_secrets

AUTH_USER_MODEL = 'cbstg_app.CustomUser'

env = environ.Env()
if env("APPLICATION_SETTINGS", default=None):
    env.read_env(io.StringIO(os.environ.get("APPLICATION_SETTINGS", None)))
else:
    env_file = BASE_DIR / ".env"
    env.read_env(env_file)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG", default=False)
DATABASES = {"default": env.db()}
SERVICE_NAME = env("SERVICE_NAME", default=None)

try:
    _, PROJECT_ID = google.auth.default()
except google.auth.exceptions.DefaultCredentialsError:
    PROJECT_ID = env("PROJECT_ID", default=None)

try:
    response = requests.get(
        "http://metadata.google.internal/computeMetadata/v1/instance/region",
        headers={"Metadata-Flavor": "Google"},
    )
    REGION = response.text.split("/")[-1]
except requests.exceptions.ConnectionError:
    REGION = None

if all((PROJECT_ID, REGION, SERVICE_NAME)):
    service_path = f"projects/{PROJECT_ID}/locations/{REGION}/services/{SERVICE_NAME}"
    client = ServicesClient()
    service_uri = client.get_service(name=service_path).uri
    ALLOWED_HOSTS = [urlparse(service_uri).netloc]
    CSRF_TRUSTED_ORIGINS = [service_uri]
else:
    ALLOWED_HOSTS = ["*"]

if GS_BUCKET_NAME := env("MEDIAFILES_BUCKET_NAME", default=None):

    if STATICFILES_BUCKET_NAME := env("STATICFILES_BUCKET_NAME", default=None):
        STORAGES = {
            "default": {
                "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
                "OPTIONS": {
                    "bucket_name": GS_BUCKET_NAME,
                },
            },
            "staticfiles": {
                "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
                "OPTIONS": {
                    "bucket_name": STATICFILES_BUCKET_NAME,
                },
            },
        }
    else:
        STORAGES = {
            "default": {
                "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
            },
            "staticfiles": {
                "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
            },
        }

else:
    SECRET_KEY = local_secrets.SECRET_KEY
    PROJECT_ID = local_secrets.PROJECT_ID
    MEDIA_URL = f"https://storage.googleapis.com/{local_secrets.GS_BUCKET_NAME}/"
    GS_BUCKET_NAME = local_secrets.GS_BUCKET_NAME

    GS_CREDENTIALS = service_account.Credentials.from_service_account_file(
        os.path.join(BASE_DIR, local_secrets.BUCKET_CREDENTIALS_PATH)
    )
    DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
            "OPTIONS": {
                "project_id": local_secrets.PROJECT_ID,
                "bucket_name": local_secrets.GS_BUCKET_NAME,
                "credentials": GS_CREDENTIALS
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
