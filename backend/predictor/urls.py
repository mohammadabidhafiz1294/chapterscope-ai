from django.urls import path
from . import views

app_name = 'predictor'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Exam paper management
    path('exams/', views.exam_list, name='exam_list'),
    path('exams/upload/', views.exam_upload, name='exam_upload'),
    path('exams/<int:pk>/', views.exam_detail, name='exam_detail'),
    path('exams/<int:pk>/process/', views.exam_process, name='exam_process'),
    path('exams/<int:pk>/analysis/', views.exam_analysis, name='exam_analysis'),
    path('exams/<int:pk>/delete/', views.exam_delete, name='exam_delete'),
    path('exams/<int:pk>/update-year/', views.exam_update_year, name='exam_update_year'),

    # Syllabus management
    path('syllabi/', views.syllabus_list, name='syllabus_list'),
    path('syllabi/upload/', views.syllabus_upload, name='syllabus_upload'),
    path('syllabi/<int:pk>/', views.syllabus_detail, name='syllabus_detail'),
    path('syllabi/<int:pk>/process/', views.syllabus_process, name='syllabus_process'),
    path('syllabi/<int:pk>/delete/', views.syllabus_delete, name='syllabus_delete'),

    # Prediction management
    path('predictions/', views.prediction_list, name='prediction_list'),
    path('predictions/create/', views.prediction_create, name='prediction_create'),
    path('predictions/<int:pk>/', views.prediction_detail, name='prediction_detail'),

    # Analysis
    path('analysis/topics/', views.topic_analysis, name='topic_analysis'),
]
