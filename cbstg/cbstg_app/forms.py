from django import forms
from .models import SubmittedFile


class SubmittedFileForm(forms.ModelForm):
    class Meta:
        model = SubmittedFile
        fields = ['file']
        widgets = {
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
