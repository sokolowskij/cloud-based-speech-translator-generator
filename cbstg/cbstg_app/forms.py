from django import forms
from .models import SubmittedText, TranslatedText


class SubmittedTextForm(forms.ModelForm):
    class Meta:
        model = SubmittedText
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
