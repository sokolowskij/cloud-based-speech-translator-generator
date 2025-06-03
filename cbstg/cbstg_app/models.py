from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser


# Create your models here.

class Role(models.Model):
    role_id = models.AutoField(primary_key=True)
    role_name = models.CharField(max_length=20, unique=True)
    daily_tts_limit = models.IntegerField(default=5)
    daily_stt_limit = models.IntegerField(default=5)
    char_limit = models.IntegerField(default=300)
    audio_duration_limit = models.IntegerField(default=30)

    class Meta:
        db_table = 'roles'


class CustomUser(AbstractUser):
    role = models.ForeignKey(Role, on_delete=models.SET_DEFAULT, default=1)


class SubmittedFile(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    file = models.FileField(upload_to="textfiles/textsubmissions")
    creation_date = models.DateField(auto_now_add=True)
