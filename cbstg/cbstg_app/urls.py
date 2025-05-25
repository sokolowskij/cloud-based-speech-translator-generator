from django.urls import path

from .views import myfiles_view, submit_file, download_submitted, transcribe_audio, delete_file, synthesize_speech, \
    save_synthesized_audio, change_role

urlpatterns = [
    path("notes/", myfiles_view, name='notes_view'),
    path("notes/submit_file", submit_file, name='save_file'),
    path('notes/download_submitted/<int:file_id>/', download_submitted, name='download_submitted'),
    path('notes/transcribe_audio/<int:file_id>/', transcribe_audio, name='transcribe_audio'),
    path('notes/delete_file/<int:file_id>/', delete_file, name='delete_file'),
    path('notes/synthesize_speech/<int:file_id>/', synthesize_speech, name='synthesize_speech'),
    path('notes/save_synthesized_audio/', save_synthesized_audio, name='save_synthesized_audio'),
    path('account/', change_role, name='change_role'),
]
