from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import ExamPaper, Topic, Prediction, Syllabus

# Unregister the default User admin
admin.site.unregister(User)

# Register the default User admin with customizations
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)

@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'subject', 'uploaded_at', 'processed', 'topic_count')
    list_filter = ('subject', 'uploaded_at', 'processed', 'user')
    search_fields = ('title', 'description', 'user__username', 'subject')
    readonly_fields = ('uploaded_at', 'processed_at')
    ordering = ('-uploaded_at',)

@admin.register(ExamPaper)
class ExamPaperAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'year', 'uploaded_at', 'processed', 'topic_count')
    list_filter = ('year', 'uploaded_at', 'processed', 'user')
    search_fields = ('title', 'description', 'user__username')
    readonly_fields = ('uploaded_at', 'processed_at')
    ordering = ('-uploaded_at',)

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_source', 'frequency', 'last_seen')
    list_filter = ('last_seen',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'last_seen')

    def get_source(self, obj):
        if obj.syllabus:
            return f"Syllabus: {obj.syllabus.title}"
        elif obj.exam_paper:
            return f"Exam: {obj.exam_paper.title}"
        return "Unknown"
    get_source.short_description = 'Source'
    get_source.admin_order_field = 'name'

@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_source', 'created_at', 'accuracy_score', 'prediction_type')
    list_filter = ('prediction_type', 'created_at', 'user')
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at', 'quantum_result', 'classical_result')

    def get_source(self, obj):
        if obj.syllabus:
            return f"Syllabus: {obj.syllabus.title}"
        elif obj.exam_paper:
            return f"Exam: {obj.exam_paper.title}"
        return "Unknown"
    get_source.short_description = 'Source'
    get_source.admin_order_field = 'created_at'

# Custom admin site header
admin.site.site_header = 'EduQuantum Predictor Administration'
admin.site.site_title = 'EduQuantum Admin'
admin.site.index_title = 'EduQuantum Dashboard'
