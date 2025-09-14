# EduQuantum Predictor API Documentation

## Overview

The EduQuantum Predictor is a hybrid quantum-AI system for analyzing educational content and predicting exam question patterns. This document describes the API endpoints available for integration.

## Base URL

```text
/api/v1/
```

## Authentication

All API endpoints require authentication. Use Django's session authentication or token authentication.

## Endpoints

### Dashboard Data API

**GET** `/predictor/api/dashboard-data/`

Returns real-time dashboard statistics and chart data.

**Response:**

```json
{
    "total_syllabi": 5,
    "total_exams": 12,
    "total_topics": 45,
    "total_predictions": 8,
    "topic_names": ["Python", "Java", "Data Structures"],
    "topic_frequencies": [25.5, 20.3, 15.2],
    "topics_data": [
        {
            "id": 1,
            "name": "Python",
            "frequency": 25.5,
            "description": "Python programming language",
            "category": "programming",
            "syllabus_title": "Computer Science 101",
            "confidence": 0.85
        }
    ]
}
```

### Syllabus Management

#### List Syllabi

**GET** `/predictor/syllabi/`

Returns paginated list of user's syllabi.

**Query Parameters:**

- `search`: Search term for filtering syllabi
- `page`: Page number for pagination

**Response:**

```json
{
    "syllabi": [
        {
            "id": 1,
            "title": "Computer Science Syllabus",
            "subject": "Computer Science",
            "uploaded_at": "2025-09-13T10:00:00Z",
            "processed": true,
            "topic_count": 15
        }
    ],
    "total_count": 1,
    "page": 1,
    "has_next": false
}
```

#### Upload Syllabus

**POST** `/predictor/syllabi/upload/`

Upload a new syllabus file for processing.

**Form Data:**

- `title`: Syllabus title (required)
- `subject`: Subject area (required)
- `description`: Optional description
- `file`: Syllabus file (PDF, DOCX, or TXT)

**Response:**

```json
{
    "status": "success",
    "message": "Syllabus uploaded successfully",
    "syllabus_id": 1
}
```

#### Process Syllabus

**POST** `/predictor/syllabi/{id}/process/`

Process an uploaded syllabus to extract topics.

**Response:**

```json
{
    "status": "success",
    "message": "Syllabus processed successfully. Found 15 topics.",
    "topic_count": 15,
    "processing_stats": {
        "text_length": 15420,
        "processing_time": 2.34,
        "ai_requests": 2
    }
}
```

### Exam Management

#### List Exams

**GET** `/predictor/exams/`

Returns paginated list of user's exam papers.

#### Upload Exam

**POST** `/predictor/exams/upload/`

Upload a new exam paper for analysis.

**Form Data:**

- `title`: Exam title (required)
- `subject`: Subject area (required)
- `description`: Optional description
- `syllabus`: Related syllabus ID (optional)
- `file`: Exam file (PDF, DOCX, or TXT)

#### Process Exam

**POST** `/predictor/exams/{id}/process/`

Analyze an uploaded exam paper.

**Response:**

```json
{
    "status": "success",
    "message": "Exam analyzed successfully. Found 25 questions.",
    "analysis_data": {
        "total_questions": 25,
        "topics_found": 8,
        "processing_time": 3.45,
        "success_rate": 92.0
    }
}
```

### Prediction Management

#### List Predictions

**GET** `/predictor/predictions/`

Returns paginated list of user's predictions.

#### Create Prediction

**POST** `/predictor/predictions/create/`

Create a new prediction based on syllabus analysis.

**Form Data:**

- `syllabus`: Syllabus ID (required)
- `prediction_type`: Type of prediction (required)
- `description`: Optional description

**Response:**

```json
{
    "status": "success",
    "message": "Prediction created successfully",
    "prediction_id": 1
}
```

### Analysis Endpoints

#### Topic Analysis

**GET** `/predictor/analysis/topics/`

Returns comprehensive topic analysis across all syllabi.

**Response:**

```json
{
    "topics": [
        {
            "id": 1,
            "name": "Python Programming",
            "frequency": 25.5,
            "trend": "increasing",
            "confidence": 0.85,
            "academic_level": "undergraduate",
            "syllabus_title": "CS 101"
        }
    ],
    "summary": {
        "total_topics": 45,
        "avg_frequency": 15.2,
        "trending_up": 12,
        "trending_down": 3
    }
}
```

## Data Models

### Syllabus

```json
{
    "id": 1,
    "title": "Computer Science Syllabus",
    "subject": "Computer Science",
    "description": "Course syllabus for CS 101",
    "uploaded_at": "2025-09-13T10:00:00Z",
    "processed": true,
    "processed_at": "2025-09-13T10:02:00Z",
    "topic_count": 15,
    "file": "/media/syllabi/cs_syllabus.pdf"
}
```

### Exam Paper

```json
{
    "id": 1,
    "title": "Midterm Exam",
    "subject": "Computer Science",
    "description": "Midterm examination",
    "uploaded_at": "2025-09-13T11:00:00Z",
    "processed": true,
    "processed_at": "2025-09-13T11:05:00Z",
    "questions_data": [...],
    "topics_covered": ["Python", "Data Structures"],
    "analysis_data": {...}
}
```

### Topic

```json
{
    "id": 1,
    "name": "Python Programming",
    "description": "Introduction to Python programming",
    "frequency": 25.5,
    "category": "programming",
    "metadata": {
        "confidence": 0.85,
        "keywords": ["python", "programming", "syntax"],
        "source_text": "Python programming fundamentals"
    },
    "syllabus": 1
}
```

### Prediction

```json
{
    "id": 1,
    "prediction_type": "comprehensive",
    "description": "Comprehensive syllabus analysis",
    "created_at": "2025-09-13T12:00:00Z",
    "accuracy_score": 85.5,
    "quantum_result": {...},
    "classical_result": {...},
    "final_prediction": {...},
    "processing_time": 5.23,
    "syllabus": 1
}
```

## Error Handling

All API endpoints return appropriate HTTP status codes:

- `200`: Success
- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `500`: Internal Server Error

Error responses include:

```json
{
    "status": "error",
    "message": "Detailed error message",
    "error_code": "ERROR_CODE"
}
```

## Rate Limiting

API endpoints are rate limited to prevent abuse:

- Authenticated users: 100 requests per minute
- File uploads: 10 uploads per hour

## File Upload Limits

- Maximum file size: 10MB
- Supported formats: PDF, DOCX, TXT
- Text extraction limit: 50,000 characters per file

## WebSocket Support

Real-time updates are available via WebSocket for long-running operations:

**URL:** `ws://localhost:8000/ws/analysis/{task_id}/`

**Messages:**

```json
{
    "type": "progress",
    "task_id": "123",
    "progress": 75,
    "message": "Processing topics..."
}
```

## SDK and Libraries

### Python Client

```python
from eduquantum_client import EduQuantumClient

client = EduQuantumClient(api_key="your_key")
result = client.analyze_syllabus(file_path="syllabus.pdf")
```

### JavaScript Client

```javascript
import { EduQuantumAPI } from 'eduquantum-js';

const api = new EduQuantumAPI({ apiKey: 'your_key' });
const result = await api.uploadExam(file);
```

## Changelog

### Version 1.0.0

- Initial release
- Basic syllabus and exam analysis
- Quantum prediction engine
- REST API endpoints
- Dashboard and visualization

## Support

For API support, please contact:

- Email: support@eduquantum.com
- Documentation: <https://docs.eduquantum.com>
- GitHub Issues: <https://github.com/eduquantum/predictor/issues>
