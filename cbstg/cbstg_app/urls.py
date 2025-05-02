from django.urls import path

from .views import mytexts_view, submit_text, download_submitted_text, submit_audio

urlpatterns = [
    path("text_to_speech/", mytexts_view, name='text_to_speech'),
    path("text_to_speech/submit_text", submit_text, name='create_new_speech_from_text'),
    path('text_to_speech/download_submitted/<int:text_id>/', download_submitted_text, name='download_submitted_text'),
    path("speech_to_text/", mytexts_view, name='speech_to_text'),
    path("speech_to_text/submit_audio", submit_audio, name='create_new_text_from_speech')
]
