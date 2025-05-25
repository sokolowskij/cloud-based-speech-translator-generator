from django.apps import AppConfig

class CbstgAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cbstg_app'

    def ready(self):
        import cbstg_app.signals  # ważne: rejestruje sygnały
