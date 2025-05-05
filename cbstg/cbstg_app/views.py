from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from google.cloud import storage, speech

from .forms import SubmittedTextForm, TranslatedTextForm
from .models import SubmittedText


@login_required
def submit_text(request):
    if request.method == 'POST':
        form = SubmittedTextForm(request.POST, request.FILES)
        if form.is_valid():
            submitted_text = form.save(commit=False)
            submitted_text.user = request.user
            submitted_text.save()
            return redirect('text_to_speech')
    else:
        form = SubmittedTextForm()
    return render(request, 'translation/submit_text.html', {'form': form})


@login_required
def download_submitted_text(request, text_id):
    try:
        submitted_text = SubmittedText.objects.get(id=text_id, user=request.user)
    except SubmittedText.DoesNotExist:
        raise Http404("File not found.")

    file_path = submitted_text.file.name
    filename = submitted_text.file.name.split("/")[-1]

    # Initialize GCS client
    if settings.SERVICE_NAME is None:  # local development
        storage_client = storage.Client(credentials=settings.GS_CREDENTIALS)
    else:
        storage_client = storage.Client()

    bucket = storage_client.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(file_path)

    # Generate signed URL with download header
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=10),
        method="GET",
        response_disposition=f'attachment; filename="{filename}"',
    )

    return HttpResponseRedirect(url)


@login_required(login_url="/login")
def mytexts_view(request):
    user = User.objects.get(pk=request.user.id)
    try:
        texts = SubmittedText.objects.filter(user=user)
    except ObjectDoesNotExist:
        texts = None
    return render(request, 'translation/mytexts.html', {"texts_queryset": texts})

# @login_required(login_url="/login")
# def delete_text(request, pk):
#     user = User.objects.get(pk=request.user.id)
#     note = Note.objects.get(user=user, pk=pk)
#     note.delete()
#
#     return redirect("mynotes_view")
@login_required(login_url="/login")
def myaudio_view(request):
    user = User.objects.get(pk=request.user.id)
    try:
        texts = SubmittedText.objects.filter(user=user)
    except ObjectDoesNotExist:
        texts = None
    return render(request, 'speechtotext/myaudio.html', {"texts_queryset": texts})


@login_required(login_url="/login")
def submit_audio(request):
    if request.method == 'POST' and request.FILES.get('audio_file'):
        client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=request.FILES['audio_file'].read())
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            language_code="pl-PL"
        )
        response = client.recognize(config=config, audio=audio)

        transcript = " ".join([result.alternatives[0].transcript for result in response.results])
        return JsonResponse({"transcript": transcript})
    return render(request, "speechtotext/transcribe_audio.html")

