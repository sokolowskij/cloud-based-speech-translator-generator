import base64
import io
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from google.cloud import storage, speech, texttospeech
from pydub import AudioSegment

from .forms import SubmittedFileForm
from .models import SubmittedFile


@login_required
def submit_file(request):
    if request.method == 'POST':
        print("Post called")
        form = SubmittedFileForm(request.POST, request.FILES)
        if form.is_valid():
            print("Form is valid")
            submitted_text = form.save(commit=False)
            submitted_text.user = request.user
            try:
                submitted_text.save()
            except Exception as e:
                print(e)
            return redirect('notes_view')
    else:
        form = SubmittedFileForm()
    return render(request, 'notes/submit_file.html', {'form': form})


@login_required
def download_submitted(request, file_id):
    try:
        submitted_text = SubmittedFile.objects.get(id=file_id, user=request.user)
        print("Submitted text")
    except SubmittedFile.DoesNotExist:
        raise Http404("File not found.")
    try:
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
    except Exception as e:
        print(e)

    return HttpResponseRedirect(url)


@login_required(login_url="/login")
def myfiles_view(request):
    user = request.user

    try:
        # Get all submitted files for the user
        files = SubmittedFile.objects.filter(user=user)

        # Define audio extensions
        audio_extensions = [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".webm"]

        # Build a Q object to OR-match all audio extensions
        audio_query = Q()
        for ext in audio_extensions:
            audio_query |= Q(file__iendswith=ext)

        # Filter audio and text files
        audio_files = files.filter(audio_query)
        text_files = files.exclude(audio_query)

    except ObjectDoesNotExist:
        audio_files = None
        text_files = None

    return render(
        request,
        "notes/myfiles.html",
        {"audio_files": audio_files, "text_files": text_files}
    )


@require_POST
@login_required(login_url="/login")
def delete_file(request, file_id):
    try:
        file = SubmittedFile.objects.get(id=file_id, user=request.user)
        file.file.delete()  # Deletes the file from storage
        file.delete()  # Deletes the database record
    except SubmittedFile.DoesNotExist:
        print("File not found.")
    return redirect('notes_view')


@login_required(login_url="/login")
def transcribe_audio(request, file_id):
    transcript = None
    error = None
    if request.method == 'GET':
        try:
            submitted_file = SubmittedFile.objects.get(id=file_id, user=request.user)
            print("Submitted text")
        except SubmittedFile.DoesNotExist:
            raise Http404("File not found.")
        try:
            client = speech.SpeechClient()
            with default_storage.open(submitted_file.file.name, "rb") as audio_file:
                audio_data = io.BytesIO(audio_file.read())

            # Convert stereo to mono
            audio = AudioSegment.from_file(audio_data)
            audio = audio.set_channels(1)  # Convert to mono
            audio = audio.set_frame_rate(16000)  # Standardize sample rate

            # Save converted audio to memory
            wav_data = io.BytesIO()
            audio.export(wav_data, format="wav")
            wav_data.seek(0)

            recognition_audio = speech.RecognitionAudio(content=wav_data.read())
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                language_code="en-US",
                sample_rate_hertz=16000,  # Standardized sample rate
                enable_automatic_punctuation=True,
            )

            response = client.recognize(config=config, audio=recognition_audio)
            transcript = " ".join([result.alternatives[0].transcript for result in response.results])
        except Exception as e:
            print("Transcription failed:", e)
            error = str(e)

        return render(request, "notes/text/viewText.html", {
            "transcript": transcript,
            "error": error,
        })
    elif request.method == 'POST':
        filename = request.POST.get('filename', 'transcription.txt')
        if not filename.endswith('.txt'):
            filename += '.txt'

        try:
            # Save the transcript as a new SubmittedFile (text)
            new_file = SubmittedFile(
                user=request.user,
                file=None  # We will set this in memory below
            )

            # Create the file in memory

            new_file.file.save(filename, ContentFile(request.POST.get('transcript', '').encode()), save=False)
            new_file.save()
            return redirect('notes_view')
        except Exception as e:
            error = f"Failed to save transcription: {e}"
        return render(request, "notes/text/viewText.html", {
            "transcript": transcript,
            "error": error,
        })

    return redirect('notes_view')


@login_required
def synthesize_speech(request, file_id):
    try:
        text_file = SubmittedFile.objects.get(id=file_id, user=request.user)

        with default_storage.open(text_file.file.name, "r") as f:
            text = f.read()

        if not text:
            raise ValueError("File is empty.")

        # Initialize the TTS client
        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        # Return as downloadable audio file
        # response_audio = HttpResponse(response.audio_content, content_type="audio/mpeg")
        # response_audio["Content-Disposition"] = f'attachment; filename="synthesized_{file_id}.mp3"'
        # return response_audio
        # Save audio to a temporary file
        # Store audio in memory
        audio_buffer = io.BytesIO(response.audio_content)
        audio_base64 = base64.b64encode(audio_buffer.getvalue()).decode('utf-8')

        # Show playback and allow user to save
        return render(request, "notes/audio/viewAudio.html", {
            "audio_data": audio_base64,
            "file_id": file_id,
            "text": text
        })
    except (SubmittedFile.DoesNotExist, ValueError) as e:
        print(e)
        raise Http404("Text file not found or invalid.")


@login_required
@require_POST
def save_synthesized_audio(request):
    file_id = request.POST.get("file_id")
    filename = request.POST.get("filename")
    audio_data = request.POST.get("audio_data")

    if not filename or not audio_data:
        return HttpResponseBadRequest("Missing filename or audio data.")

    try:
        decoded_audio = base64.b64decode(audio_data)
        path = default_storage.save(f"submitted/{filename}.mp3", ContentFile(decoded_audio))
        SubmittedFile.objects.create(user=request.user, file=path, creation_date=timezone.now())
    except Exception as e:
        return HttpResponse(f"Failed to save audio: {e}", status=500)

    return redirect("notes_view")
