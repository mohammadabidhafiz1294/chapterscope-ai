"""
URL configuration for eduquantum project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from predictor import views as predictor_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('predictor.urls', namespace='predictor')),

    # Authentication URLs
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),

    # API endpoints
    path('api/', include([
        # Anonymous liveness probe - no secrets, no stack traces.
        path('health/', predictor_views.health_check, name='health'),
        path('auth/login/', predictor_views.api_login, name='api_login'),
        path('auth/register/', predictor_views.api_register, name='api_register'),
        path('auth/logout/', predictor_views.api_logout, name='api_logout'),
        path('auth/validate/', predictor_views.api_validate_token, name='api_validate_token'),
        path('auth/csrf-token/', predictor_views.api_csrf_token, name='api_csrf_token'),
        # API-specific endpoints
        path('dashboard-data/', predictor_views.dashboard_data_api, name='dashboard_data_api'),
        # Phase 2 course-notebook REST API (DRF serializers + permissions).
        path('notebooks/', include('predictor.api_urls')),
    ])),
]
