from django import forms
from .models import ExamPaper, Syllabus

class ExamPaperUploadForm(forms.ModelForm):
    """Form for uploading exam papers."""

    class Meta:
        model = ExamPaper
        fields = ['title', 'description', 'file', 'year']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter exam paper title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe the exam paper'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt'
            }),
            'year': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '2000',
                'max': '2030',
                'placeholder': 'Exam year'
            })
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def clean_year(self):
        year = self.cleaned_data.get('year')
        if year and (year < 2000 or year > 2030):
            raise forms.ValidationError('Year must be between 2000 and 2030')
        return year

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user:
            instance.user = self.user
        if commit:
            instance.save()
        return instance


class SyllabusUploadForm(forms.ModelForm):
    """Form for uploading syllabi."""

    class Meta:
        model = Syllabus
        fields = ['title', 'description', 'file', 'subject']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter syllabus title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe the syllabus'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt'
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Subject (e.g., Mathematics, Physics, Computer Science)'
            })
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user:
            instance.user = self.user
        if commit:
            instance.save()
        return instance


class PredictionForm(forms.Form):
    """Form for creating predictions."""

    exam_paper = forms.ModelChoiceField(
        queryset=None,
        empty_label="Select an exam paper",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    prediction_type = forms.ChoiceField(
        choices=[
            ('HYBRID', 'Hybrid (Quantum + Classical)'),
            ('QUANTUM', 'Quantum Only'),
            ('CLASSICAL', 'Classical Only'),
        ],
        initial='HYBRID',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional description for this prediction'
        })
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['exam_paper'].queryset = ExamPaper.objects.filter(
                user=self.user
            )
