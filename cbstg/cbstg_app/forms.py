from django import forms
from .models import SubmittedFile, TranslatedText


class SubmittedFileForm(forms.ModelForm):
    class Meta:
        model = SubmittedFile
        fields = ['file']
        widgets = {
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class TranslatedTextForm(forms.ModelForm):
    class Meta:
        model = TranslatedText
        fields = ['file']
        widgets = {
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
