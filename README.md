# EduQuantum Predictor

A hybrid quantum-AI system for analyzing educational content and predicting exam question patterns using advanced machine learning and quantum computing algorithms.

## Features

- **AI-Powered Analysis**: Uses Google Gemini API for intelligent topic extraction and content analysis
- **Quantum Prediction Engine**: Implements Variational Quantum Eigensolver (VQE) for pattern prediction
- **Multi-Format Support**: Processes PDF, DOCX, and TXT files
- **Real-time Dashboard**: Interactive visualizations with Chart.js
- **Comprehensive Testing**: Full test suite with unit, integration, and performance tests
- **REST API**: Complete API for integration with other systems
- **Docker Support**: Containerized deployment with Docker Compose

## Quick Start

### Prerequisites
- Python 3.8+
- PostgreSQL or MySQL
- Google Gemini API key

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/eduquantum-predictor.git
   cd eduquantum-predictor
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Setup database**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

6. **Run the application**
   ```bash
   python manage.py runserver
   ```

Visit `http://localhost:8000` to access the application.

## Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up --build

# Run migrations
docker-compose exec web python manage.py migrate
```

## API Documentation

The system provides a comprehensive REST API. See `backend/API_DOCUMENTATION.md` for detailed endpoint documentation.

## Project Structure

```
eduquantum-predictor/
├── backend/                 # Django backend application
│   ├── eduquantum_predictor/  # Main Django project
│   ├── predictor/            # Main app
│   ├── services/            # Core business logic
│   ├── static/              # Static files
│   ├── templates/           # HTML templates
│   └── tests/               # Test suite
├── frontend/               # React frontend (future)
├── docs/                   # Documentation
├── scripts/                # Utility scripts
├── requirements.txt        # Python dependencies
├── docker-compose.yml      # Docker configuration
├── Dockerfile             # Docker image definition
└── DEPLOYMENT_GUIDE.md    # Deployment instructions
```

## Core Components

### Services
- **GeminiClient**: Google Gemini API integration
- **QuestionSegmenter**: Text segmentation and preprocessing
- **QuestionClassifier**: Topic classification
- **TopicFrequencyTracker**: Frequency analysis
- **ExamAnalysisService**: Exam paper analysis
- **QuantumPredictionEngine**: Quantum computing predictions
- **QuantumCircuitConstructor**: Qiskit circuit construction
- **EduQuantumIntegrator**: Main integration service

### Models
- **Syllabus**: Course syllabus information
- **ExamPaper**: Exam paper data
- **Topic**: Extracted topics with metadata
- **Prediction**: Quantum prediction results

## Configuration

### Environment Variables

```env
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/db

# Security
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=localhost,yourdomain.com

# AI Services
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-1.5-pro

# Quantum Computing
QISKIT_IBMQ_TOKEN=your-ibmq-token

# File Upload
MEDIA_ROOT=/path/to/media
STATIC_ROOT=/path/to/static
```

## Testing

Run the complete test suite:

```bash
# Unit tests
python manage.py test tests.test_services

# Integration tests
python manage.py test tests.test_integration

# All tests
python manage.py test
```

## Development

### Code Quality
- Black for code formatting
- Flake8 for linting
- Pre-commit hooks for quality checks

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Deployment

See `DEPLOYMENT_GUIDE.md` for comprehensive deployment instructions including:
- Docker deployment
- Production server setup
- Cloud deployment (AWS, Heroku)
- Monitoring and maintenance

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- **Documentation**: See `docs/` directory
- **API Docs**: `backend/API_DOCUMENTATION.md`
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions

## Roadmap

### Version 1.1.0
- React frontend integration
- Advanced quantum algorithms
- Real-time collaboration features
- Mobile application

### Version 1.2.0
- Multi-language support
- Advanced analytics dashboard
- Integration with learning management systems
- API rate limiting and caching

## Acknowledgments

- Google Gemini for AI capabilities
- Qiskit for quantum computing framework
- Django for robust web framework
- Open source community for invaluable tools and libraries
