from django import forms
from django.conf import settings

from .models import CourseNotebook, ExamPaper, Syllabus


def validate_upload_file(uploaded_file):
    """Validate upload extension and size against project settings.

    Used by the exam-paper and syllabus upload forms (the existing upload
    flow). Raises forms.ValidationError on failure.
    """
    if uploaded_file is None:
        raise forms.ValidationError('No file was submitted.')

    # Extension check (lowercase, dot-insensitive).
    name = getattr(uploaded_file, 'name', '') or ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    allowed = getattr(settings, 'ALLOWED_FILE_TYPES', ['pdf', 'doc', 'docx', 'txt'])
    if ext not in allowed:
        raise forms.ValidationError(
            f'Unsupported file type "{ext}". Allowed: {", ".join(allowed)}.'
        )

    max_size = getattr(settings, 'MAX_FILE_SIZE', 10 * 1024 * 1024)
    if uploaded_file.size and uploaded_file.size > max_size:
        raise forms.ValidationError(
            f'File is too large ({uploaded_file.size} bytes). '
            f'Maximum allowed is {max_size} bytes.'
        )
    return uploaded_file


def _notebook_queryset(user):
    if not user or not user.is_authenticated:
        return CourseNotebook.objects.none()
    return CourseNotebook.objects.filter(
        owner=user, status=CourseNotebook.STATUS_ACTIVE
    ).order_by('title')


class ExamPaperUploadForm(forms.ModelForm):
    """Form for uploading exam papers."""

    notebook = forms.ModelChoiceField(
        queryset=CourseNotebook.objects.none(),
        required=False,
        empty_label="— No notebook (unassigned) —",
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Optionally attach this exam paper to one of your course notebooks.",
    )

    class Meta:
        model = ExamPaper
        fields = ['title', 'description', 'file', 'year', 'notebook']
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
        self.fields['notebook'].queryset = _notebook_queryset(self.user)

    def clean_year(self):
        year = self.cleaned_data.get('year')
        if year and (year < 2000 or year > 2030):
            raise forms.ValidationError('Year must be between 2000 and 2030')
        return year

    def clean_file(self):
        return validate_upload_file(self.cleaned_data.get('file'))

    def clean(self):
        cleaned = super().clean()
        notebook = cleaned.get('notebook')
        # Ownership: only the request user's notebooks are selectable; the
        # queryset already enforces this, but double-check for safety.
        if notebook is not None and self.user and notebook.owner_id != self.user.id:
            self.add_error('notebook', 'You can only attach to your own notebook.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user:
            instance.user = self.user
        if commit:
            instance.save()
        return instance


class SyllabusUploadForm(forms.ModelForm):
    """Form for uploading syllabi."""

    notebook = forms.ModelChoiceField(
        queryset=CourseNotebook.objects.none(),
        required=False,
        empty_label="— No notebook (unassigned) —",
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Optionally attach this syllabus to one of your course notebooks.",
    )

    class Meta:
        model = Syllabus
        fields = ['title', 'description', 'file', 'subject', 'notebook']
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
        self.fields['notebook'].queryset = _notebook_queryset(self.user)

    def clean_file(self):
        return validate_upload_file(self.cleaned_data.get('file'))

    def clean(self):
        cleaned = super().clean()
        notebook = cleaned.get('notebook')
        if notebook is not None and self.user and notebook.owner_id != self.user.id:
            self.add_error('notebook', 'You can only attach to your own notebook.')
        return cleaned

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


class ExamDeleteForm(forms.Form):
    """Form for confirming exam paper deletion."""
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        label='I confirm that I want to delete this exam paper permanently. This action cannot be undone.'
    )


class ExamYearUpdateForm(forms.Form):
    """Form for updating exam paper year."""
    year = forms.IntegerField(
        min_value=1900,
        max_value=2100,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new year'
        }),
        help_text='Enter the correct year for this exam paper'
    )

    def __init__(self, *args, **kwargs):
        self.exam_paper = kwargs.pop('exam_paper', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.exam_paper:
            self.fields['year'].initial = self.exam_paper.year

    def clean_year(self):
        year = self.cleaned_data.get('year')
        if year and self.exam_paper and self.user:
            # Check for unique constraint
            existing_exam = ExamPaper.objects.filter(
                user=self.user,
                title=self.exam_paper.title,
                year=year
            ).exclude(pk=self.exam_paper.pk).first()
            
            if existing_exam:
                raise forms.ValidationError(
                    f'An exam paper with the title "{self.exam_paper.title}" already exists for year {year}.'
                )
        return year
