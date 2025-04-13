from django.urls import path

from .views import mytexts_view, submit_text, download_submitted_text

urlpatterns = [
    path("text/", mytexts_view, name='text_translations_view'),
    path("text/submit_text", submit_text, name='create_new_text_translation_view'),
    path('text/download/<int:text_id>/', download_submitted_text, name='download_submitted_text'),
]