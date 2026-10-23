# ChapterScope AI Django backend

## Overview

EduQuantum is a Django-based educational analytics system that provides quantum computing and AI-powered exam question analysis. This document provides comprehensive guidance for connecting to and using the EduQuantum backend API.

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- MySQL 8.0+
- Node.js 16+ (for frontend)
- Git

### Backend Setup

1. **Clone and navigate to the project:**
   ```bash
   git clone <repository-url>
   cd Hybrid-Quantum-AI-Exam-Questions-Analysics/backend
   ```

2. **Create and activate virtual environment:**
   ```bash
   python3 -m venv ../hybrid-venv
   source ../hybrid-venv/bin/activate  # On Windows: ../hybrid-venv/Scripts/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up MySQL database:**
   ```bash
   # Make sure MySQL is running
   mysql -u root -p
   CREATE DATABASE eduquantum;
   ```

5. **Configure environment variables:**
   Create a `.env` file in the backend directory:
   ```env
   SECRET_KEY=your-secret-key-here
   DEBUG=True
   DATABASE_URL=mysql://user:password@localhost:3307/eduquantum
   GEMINI_API_KEY=your-gemini-api-key
   ```

6. **Run migrations:**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

7. **Create superuser:**
   ```bash
   python manage.py createsuperuser
   ```

8. **Start the development server:**
   ```bash
   python manage.py runserver 8001
   ```

### Frontend Setup

1. **Navigate to frontend directory:**
   ```bash
   cd ../frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure API URL:**
   Create a `.env` file in the frontend directory:
   ```env
   REACT_APP_API_URL=http://localhost:8001
   ```

4. **Start the development server:**
   ```bash
   npm start
   ```

## 📡 API Endpoints

### Base URL
```
http://localhost:8001
```

### Authentication Endpoints

#### POST /api/auth/login/
Login user with credentials.

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Login successful",
  "user": {
    "id": 1,
    "username": "string",
    "email": "string",
    "first_name": "string",
    "last_name": "string"
  }
}
```

#### POST /api/auth/register/
Register a new user.

**Request Body:**
```json
{
  "username": "string",
  "email": "string",
  "password": "string",
  "first_name": "string",
  "last_name": "string"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Registration successful",
  "user": {
    "id": 1,
    "username": "string",
    "email": "string",
    "first_name": "string",
    "last_name": "string"
  }
}
```

#### POST /api/auth/logout/
Logout current user.

**Response:**
```json
{
  "success": true,
  "message": "Logout successful"
}
```

#### GET /api/auth/csrf-token/
Get CSRF token for form submissions.

**Response:**
```json
{
  "csrf_token": "string"
}
```

### Syllabus Management

#### GET /syllabi/
List all syllabi for the authenticated user.

#### POST /syllabi/upload/
Upload a new syllabus document.

**Request:** Multipart form data with file

#### GET /syllabi/{id}/
Get syllabus details.

#### POST /syllabi/{id}/process/
Process uploaded syllabus for analysis.

### Exam Paper Management

#### GET /exams/
List all exam papers for the authenticated user.

#### POST /exams/upload/
Upload a new exam paper.

**Request:** Multipart form data with file

#### GET /exams/{id}/
Get exam paper details.

#### POST /exams/{id}/process/
Process uploaded exam paper for analysis.

#### GET /exams/{id}/analysis/
Get analysis results for exam paper.

### Prediction Management

#### GET /predictions/
List all predictions for the authenticated user.

#### POST /predictions/create/
Create a new prediction.

#### GET /predictions/{id}/
Get prediction details.

### Analysis Endpoints

#### GET /analysis/topics/
Get topic analysis data.

#### GET /api/dashboard-data/
Get dashboard data (API endpoint).

## 🔐 Authentication

### Session-Based Authentication

The API uses Django's session-based authentication. After successful login:

1. **CSRF Token:** Include in POST requests
2. **Session Cookie:** Automatically handled by browser
3. **Authorization Header:** `Bearer {token}` (optional for API calls)

### Frontend Integration

#### Axios Configuration

```typescript
import axios from 'axios';

// Set base URL
axios.defaults.baseURL = 'http://localhost:8001';

// Add request interceptor for auth token
axios.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('authToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Add response interceptor for error handling
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized access
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

#### Login Implementation

```typescript
const login = async (username: string, password: string) => {
  try {
    const response = await axios.post('/api/auth/login', {
      username,
      password
    });

    if (response.data.success) {
      localStorage.setItem('authToken', response.data.token);
      // Redirect to dashboard
      window.location.href = '/dashboard';
    }
  } catch (error) {
    console.error('Login failed:', error);
  }
};
```

## 📁 File Upload

> **Current authentication note:** The canonical frontend uses Django
> session-cookie authentication with `withCredentials` and CSRF tokens. It
> does not store JWT/mock tokens in `localStorage`. Older examples elsewhere
> in this legacy document are historical and must not be copied into a
> deployment.

### Supported File Types

- **Syllabus:** PDF, DOC, DOCX, TXT
- **Exam Papers:** PDF, DOC, DOCX, TXT
- **Max File Size:** 10MB

### Upload Example

```typescript
const uploadFile = async (file: File, type: 'syllabus' | 'exam') => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', file.name);

  const endpoint = type === 'syllabus' ? '/syllabi/upload/' : '/exams/upload/';

  try {
    const response = await axios.post(endpoint, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    return response.data;
  } catch (error) {
    console.error('Upload failed:', error);
    throw error;
  }
};
```

## 🛠️ Development

### Project Structure

```
backend/
├── eduquantum/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── predictor/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── forms.py
│   └── templates/
├── requirements.txt
└── manage.py

frontend/
├── src/
│   ├── components/
│   ├── contexts/
│   ├── services/
│   └── pages/
├── package.json
└── tsconfig.json
```

### Environment Variables

#### Backend (.env)
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
DATABASE_URL=mysql://user:password@localhost:3307/eduquantum
GEMINI_API_KEY=your-gemini-api-key
QISKIT_BACKEND=aer_simulator
```

#### Frontend (.env)
```env
REACT_APP_API_URL=http://localhost:8001
```

### Database Configuration

The application uses MySQL with the following connection settings:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'eduquantum',
        'USER': 'your-username',
        'PASSWORD': 'your-password',
        'HOST': 'localhost',
        'PORT': '3307',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        }
    }
}
```

## 🧪 Testing

### Running Tests

```bash
# Backend tests
cd backend
python manage.py test

# Frontend tests
cd frontend
npm test
```

### API Testing with cURL

```bash
# Get CSRF token
curl -X GET http://localhost:8001/api/auth/csrf-token/

# Login
curl -X POST http://localhost:8001/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass123"}'

# Upload file
curl -X POST http://localhost:8001/syllabi/upload/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/file.pdf" \
  -F "title=Sample Syllabus"
```

## 🚀 Deployment

### Production Setup

1. **Set DEBUG=False** in settings.py
2. **Configure production database**
3. **Set up static files serving**
4. **Configure CORS for production domain**
5. **Set up HTTPS**

### Docker Deployment

```dockerfile
# Dockerfile for backend
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

## 🐛 Troubleshooting

### Common Issues

#### 1. CORS Errors
- Ensure `CORS_ALLOWED_ORIGINS` includes your frontend URL
- Check that `django-cors-headers` is installed and configured

#### 2. CSRF Token Issues
- Include CSRF token in POST requests
- Ensure cookies are enabled in browser

#### 3. Authentication Failures
- Verify user credentials
- Check that user account is active
- Ensure session middleware is properly configured

#### 4. File Upload Issues
- Check file size limits
- Verify supported file types
- Ensure proper permissions on upload directory

### Debug Mode

Enable debug logging in settings.py:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'predictor': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

## 📞 Support

For issues and questions:
1. Check the troubleshooting section above
2. Review Django and React documentation
3. Check server logs for detailed error messages
4. Ensure all dependencies are properly installed

## 📝 API Versioning

Current API version: v1

All endpoints are prefixed with `/api/` for API-specific routes.
Regular web routes use standard Django URL patterns.

---

**Last Updated:** September 13, 2025
**API Version:** 1.0.0
