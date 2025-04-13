from django.db import models
from django.contrib.auth.models import User

# Create your models here.


class SubmittedText(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to="textfiles/textsubmissions")
    creation_date = models.DateField(auto_now_add=True)


class TranslatedText(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to="textfiles/texttranslations")
    creation_date = models.DateField(auto_now_add=True)
