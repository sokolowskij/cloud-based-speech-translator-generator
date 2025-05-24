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
from google.cloud import translate_v2 as translate
import soundfile as sf
import numpy as np
from scipy.signal import resample

from .forms import SubmittedFileForm
from .models import SubmittedFile
import logging

logger = logging.getLogger('cbstg')  # Use your app's logger


@login_required
def submit_file(request):
    if request.method == 'POST':
        logger.info("File submittion")
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
    except SubmittedFile.DoesNotExist as e:
        logger.error(f"Error in download_submitted: {e}")
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
        logger.info("Generated download url")
    except Exception as e:
        logger.error(f"Error in download_submitted: {e}")

    return HttpResponseRedirect(url)


@login_required(login_url="/login")
def myfiles_view(request):
    user = request.user

    try:
        # Get all submitted files for the user
        files = SubmittedFile.objects.filter(user=user).order_by("-creation_date")

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
        logger.info("No file objects present")
        audio_files = None
        text_files = None
    logger.info("Rendering myfiles view")

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
        logger.info(f"Deleted file {file_id}")

    except SubmittedFile.DoesNotExist:
        logger.info(f"File {file_id} to be deleted not found")
    return redirect('notes_view')


@login_required(login_url="/login")
def transcribe_audio(request, file_id):
    transcript = None
    err1 = None
    err2 = None
    if request.method == 'GET':
        try:
            submitted_file = SubmittedFile.objects.get(id=file_id, user=request.user)
            input_lang = request.GET.get("input_lang", "en")
            target_lang = request.GET.get("target_lang", "en")
            logger.info(f"File submitted for transcription")

        except SubmittedFile.DoesNotExist:
            raise Http404("File not found.")
        try:
            client = speech.SpeechClient()
            logger.info(f"Connecting to SpeechClient")
            with default_storage.open(submitted_file.file.name, "rb") as audio_file:
                audio_data = io.BytesIO(audio_file.read())

            # Read the audio file
            audio_data, sample_rate = sf.read(audio_data)  # or .flac, .ogg, etc.

            # If stereo, convert to mono by averaging channels
            if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
                audio_data = np.mean(audio_data, axis=1)

            # Resample to 16000 Hz if needed
            target_rate = 16000
            if sample_rate != target_rate:
                num_samples = int(len(audio_data) * target_rate / sample_rate)
                audio_data = resample(audio_data, num_samples)
                sample_rate = target_rate

            # Save converted audio to memory
            wav_data = io.BytesIO()
            sf.write(wav_data, audio_data, sample_rate, format='WAV')
            wav_data.seek(0)

            recognition_audio = speech.RecognitionAudio(content=wav_data.read())
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                language_code=input_lang,
                sample_rate_hertz=16000,  # Standardized sample rate
                enable_automatic_punctuation=True,
            )

            response = client.recognize(config=config, audio=recognition_audio)
            logger.info(f"Getting response from SpeechClient")
            transcript = " ".join([result.alternatives[0].transcript for result in response.results])

            if target_lang != input_lang:
                transcript, err1 = translate_text(transcript, target_lang)
        except Exception as e:
            err2 = "Transcription failed: " + str(e)
            logger.error(err2)

        return render(request, "notes/text/viewText.html", {
            "transcript": transcript,
            "error": err1 or err2 if (err1 and err2) is None else err1 + "\n" + err2,
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
            err2 = f"Failed to save transcription: {e}"
            logger.error(err2)

        return render(request, "notes/text/viewText.html", {
            "transcript": transcript,
            "error": err2,
        })

    return redirect('notes_view')


@login_required
def synthesize_speech(request, file_id):
    err1 = None
    try:
        text_file = SubmittedFile.objects.get(id=file_id, user=request.user)
        input_lang = request.GET.get("input_lang", "en")
        target_lang = request.GET.get("target_lang", "en")

        with default_storage.open(text_file.file.name, "r") as f:
            text = f.read()

        if not text:
            raise ValueError("File is empty.")

        if target_lang != input_lang:
            text, err1 = translate_text(text, target_lang)
            text = text.encode("utf-8")
            logger.info(f"Error while translating text: {err1}")

        # Initialize the TTS client
        logger.info(f"Connecting to TextToSpeechClient")
        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code=target_lang,
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        logger.info(f"Getting response from TextToSpeechClient")
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
            "text": text,
            "error": err1,
        })
    except (SubmittedFile.DoesNotExist, ValueError) as e:
        logger.error(f"Error in synthesize_speech {e}")
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
        logger.error(f"Failed to save audio: {e}")
        return HttpResponse(f"Failed to save audio: {e}", status=500)

    return redirect("notes_view")


def translate_text(text, target_language='en'):
    try:
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        logger.info(f"Connecting to translate Client")
        client = translate.Client()
        result = client.translate(text, target_language=target_language)
        return result["translatedText"], None
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return text, "Translation failed: " + str(e) + "\n"
