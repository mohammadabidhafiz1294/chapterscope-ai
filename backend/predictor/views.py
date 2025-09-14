from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
import json
import logging

from .models import ExamPaper, Topic, Prediction, Syllabus
from .forms import ExamPaperUploadForm, PredictionForm, SyllabusUploadForm

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    """Main dashboard view showing user's exams, syllabi, and predictions."""
    exam_papers = ExamPaper.objects.filter(user=request.user).order_by('-uploaded_at')[:5]
    syllabi = Syllabus.objects.filter(user=request.user).order_by('-uploaded_at')[:5]
    predictions = Prediction.objects.filter(user=request.user).order_by('-created_at')[:5]

    # Get topic data for charts (from both exam papers and syllabi)
    exam_topics = Topic.objects.filter(exam_paper__user=request.user).order_by('-frequency')[:20]
    syllabus_topics = Topic.objects.filter(syllabus__user=request.user).order_by('-frequency')[:20]

    # Combine and deduplicate topics
    all_topics = list(exam_topics) + list(syllabus_topics)
    unique_topics = {}
    for topic in all_topics:
        if topic.name not in unique_topics or topic.frequency > unique_topics[topic.name].frequency:
            unique_topics[topic.name] = topic

    topics = list(unique_topics.values())[:20]

    # Prepare chart data
    topic_names = [topic.name for topic in topics]
    topic_frequencies = [topic.frequency for topic in topics]

    context = {
        'exam_papers': exam_papers,
        'syllabi': syllabi,
        'predictions': predictions,
        'topics': topics,
        'total_exams': ExamPaper.objects.filter(user=request.user).count(),
        'total_syllabi': Syllabus.objects.filter(user=request.user).count(),
        'total_predictions': Prediction.objects.filter(user=request.user).count(),
        'topic_names_json': json.dumps(topic_names),
        'topic_frequencies_json': json.dumps(topic_frequencies),
    }
    return render(request, 'predictor/dashboard.html', context)


@login_required
@require_POST
def exam_process(request, pk):
    """AJAX endpoint to trigger exam paper processing."""
    exam_paper = get_object_or_404(ExamPaper, pk=pk, user=request.user)

    if exam_paper.processed:
        return JsonResponse({'status': 'error', 'message': 'Exam paper already processed'})

    try:
        from .services.gemini_client import GeminiClient
        import os

        # Extract text based on file type
        file_path = exam_paper.file.path
        file_extension = os.path.splitext(file_path)[1].lower()
        exam_paper_text = ""

        if file_extension == '.txt':
            # Read text file directly
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                exam_paper_text = f.read()
        elif file_extension == '.pdf':
            # Extract text from PDF
            import PyPDF2
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    exam_paper_text += page.extract_text() + "\n"
        elif file_extension in ['.docx', '.doc']:
            # Extract text from DOCX
            import docx
            doc = docx.Document(file_path)
            for paragraph in doc.paragraphs:
                exam_paper_text += paragraph.text + "\n"
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Unsupported file type: {file_extension}. Please upload PDF, DOC, DOCX, or TXT files.'
            })

        if not exam_paper_text.strip():
            return JsonResponse({
                'status': 'error',
                'message': 'Could not extract text from the file. The file may be corrupted or empty.'
            })

        # Initialize Gemini client
        gemini_client = GeminiClient()

        # Extract topics using Gemini Pro
        result = gemini_client.extract_topics(exam_paper_text, max_topics=15)

        if result.success and result.topics:
            # Save processing results
            exam_paper.extracted_text = exam_paper_text[:1000]  # Store first 1000 chars as preview
            exam_paper.topic_count = len(result.topics)
            exam_paper.processed = True
            exam_paper.processed_at = timezone.now()
            exam_paper.save()

            # Create Topic objects
            for topic_result in result.topics:
                Topic.objects.create(
                    exam_paper=exam_paper,
                    name=topic_result.name,
                    description=topic_result.description,
                    frequency=1,  # Default frequency
                    metadata={
                        'confidence': topic_result.confidence,
                        'category': topic_result.category,
                        'keywords': topic_result.keywords,
                        'source_text': exam_paper_text[:500]  # Store sample text
                    }
                )

            return JsonResponse({
                'status': 'success',
                'message': f'Exam paper processed successfully. Found {len(result.topics)} topics.',
                'topic_count': len(result.topics),
                'processing_time': result.processing_time
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Processing failed: {result.error or "No topics extracted"}'
            })

    except ImportError as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Missing dependencies: {e}. Please install required packages.'
        })
    except Exception as e:
        logger.error(f"Error processing exam paper {pk}: {e}")
        return JsonResponse({
            'status': 'error',
            'message': f'Processing failed: {str(e)}'
        })


@login_required
def exam_list(request):
    """List all exam papers for the current user."""
    exam_papers = ExamPaper.objects.filter(user=request.user).order_by('-uploaded_at')

    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        exam_papers = exam_papers.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(exam_papers, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'predictor/exam_list.html', context)


@login_required
def exam_upload(request):
    """Upload a new exam paper."""
    if request.method == 'POST':
        form = ExamPaperUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            exam_paper = form.save()
            messages.success(request, f'Exam paper "{exam_paper.title}" uploaded successfully!')
            return redirect('predictor:exam_detail', pk=exam_paper.pk)
    else:
        form = ExamPaperUploadForm(user=request.user)

    return render(request, 'predictor/exam_upload.html', {'form': form})


@login_required
def exam_detail(request, pk):
    """Display exam paper details and analysis."""
    exam_paper = get_object_or_404(ExamPaper, pk=pk, user=request.user)

    context = {
        'exam_paper': exam_paper,
        'questions_data': exam_paper.questions_data if exam_paper.questions_data else [],
        'topics_covered': exam_paper.topics_covered if exam_paper.topics_covered else [],
    }
    return render(request, 'predictor/exam_detail.html', context)


# Syllabus Views
@login_required
def syllabus_list(request):
    """List all syllabi for the current user."""
    syllabi = Syllabus.objects.filter(user=request.user).order_by('-uploaded_at')

    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        syllabi = syllabi.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(subject__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(syllabi, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'predictor/syllabus_list.html', context)


@login_required
def syllabus_upload(request):
    """Upload a new syllabus."""
    if request.method == 'POST':
        form = SyllabusUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            syllabus = form.save()
            messages.success(request, f'Syllabus "{syllabus.title}" uploaded successfully!')
            return redirect('predictor:syllabus_detail', pk=syllabus.pk)
    else:
        form = SyllabusUploadForm(user=request.user)

    return render(request, 'predictor/syllabus_upload.html', {'form': form})


@login_required
def syllabus_detail(request, pk):
    """Display syllabus details and analysis."""
    syllabus = get_object_or_404(Syllabus, pk=pk, user=request.user)

    context = {
        'syllabus': syllabus,
        'topics_covered': syllabus.topics_covered if syllabus.topics_covered else [],
    }
    return render(request, 'predictor/syllabus_detail.html', context)


@login_required
@require_POST
def syllabus_process(request, pk):
    """AJAX endpoint to trigger syllabus processing."""
    syllabus = get_object_or_404(Syllabus, pk=pk, user=request.user)

    if syllabus.processed:
        return JsonResponse({'status': 'error', 'message': 'Syllabus already processed'})

    try:
        from .services.gemini_client import GeminiClient
        import os

        # Extract text based on file type
        file_path = syllabus.file.path
        file_extension = os.path.splitext(file_path)[1].lower()
        syllabus_text = ""

        if file_extension == '.txt':
            # Read text file directly
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                syllabus_text = f.read()
        elif file_extension == '.pdf':
            # Extract text from PDF
            import PyPDF2
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                for page in pdf_reader.pages:
                    syllabus_text += page.extract_text() + "\n"
        elif file_extension in ['.docx', '.doc']:
            # Extract text from DOCX
            import docx
            doc = docx.Document(file_path)
            for paragraph in doc.paragraphs:
                syllabus_text += paragraph.text + "\n"
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Unsupported file type: {file_extension}. Please upload PDF, DOC, DOCX, or TXT files.'
            })

        if not syllabus_text.strip():
            return JsonResponse({
                'status': 'error',
                'message': 'Could not extract text from the file. The file may be corrupted or empty.'
            })

        # Initialize Gemini client
        gemini_client = GeminiClient()

        # Extract topics using Gemini Pro
        result = gemini_client.extract_topics(syllabus_text, max_topics=20)

        if result.success and result.topics:
            # Save processing results
            syllabus.extracted_text = syllabus_text[:1000]  # Store first 1000 chars as preview
            syllabus.topic_count = len(result.topics)
            syllabus.processed = True
            syllabus.processed_at = timezone.now()
            syllabus.topics_covered = result.topics
            syllabus.save()

            # Create Topic objects
            for topic_data in result.topics:
                Topic.objects.create(
                    syllabus=syllabus,
                    name=topic_data['name'],
                    description=topic_data.get('description', ''),
                    frequency=topic_data.get('frequency', 1),
                    metadata=topic_data.get('metadata', {})
                )

            # Generate quantum predictions for the syllabus
            from .services.eduquantum_integrator import EduQuantumIntegrator
            integrator = EduQuantumIntegrator()
            prediction_result = integrator.process_syllabus_and_predict(syllabus.id, request.user.id)

            return JsonResponse({
                'status': 'success',
                'message': f'Successfully processed syllabus. Found {len(result.topics)} topics.',
                'topics_count': len(result.topics),
                'prediction_created': prediction_result.success
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Failed to extract topics from syllabus. Please try again.'
            })

    except Exception as e:
        logger.error(f"Error processing syllabus {pk}: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred while processing the syllabus: {str(e)}'
        })


@login_required
def syllabus_delete(request, pk):
    """Delete a syllabus."""
    syllabus = get_object_or_404(Syllabus, pk=pk, user=request.user)

    if request.method == 'POST':
        syllabus_title = syllabus.title
        syllabus.delete()
        messages.success(request, f'Syllabus "{syllabus_title}" has been deleted successfully!')
        return redirect('predictor:syllabus_list')

    context = {
        'syllabus': syllabus,
    }
    return render(request, 'predictor/syllabus_delete.html', context)


@login_required
def prediction_list(request):
    """List all predictions for the current user."""
    predictions = Prediction.objects.filter(user=request.user).order_by('-created_at')

    # Pagination
    paginator = Paginator(predictions, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
    }
    return render(request, 'predictor/prediction_list.html', context)


@login_required
def prediction_create(request):
    """Create a new prediction using the integration service."""
    if request.method == 'POST':
        form = PredictionForm(request.POST, user=request.user)
        if form.is_valid():
            exam_paper = form.cleaned_data['exam_paper']
            prediction_type = form.cleaned_data['prediction_type']
            description = form.cleaned_data.get('description', '')

            try:
                # Import and use the integration service
                from .services.eduquantum_integrator import EduQuantumIntegrator

                integrator = EduQuantumIntegrator()

                # Process exam paper and generate predictions
                result = integrator.process_exam_and_predict(
                    exam_paper_id=exam_paper.id,
                    user_id=request.user.id
                )

                if result.success:
                    messages.success(request, f'Prediction created successfully! Processing time: {result.processing_time:.1f}s')
                    return redirect('predictor:prediction_detail', pk=result.data['prediction_id'])
                else:
                    messages.error(request, f'Failed to create prediction: {result.error}')
                    return redirect('predictor:prediction_create')

            except ImportError as e:
                messages.error(request, f'Missing dependencies: {e}. Please install required packages.')
                return redirect('predictor:prediction_create')
            except Exception as e:
                logger.error(f"Error creating prediction: {e}")
                messages.error(request, 'An error occurred while creating the prediction. Please try again.')
                return redirect('predictor:prediction_create')
    else:
        form = PredictionForm(user=request.user)

    return render(request, 'predictor/prediction_create.html', {'form': form})


@login_required
def prediction_detail(request, pk):
    """Display prediction details and results."""
    prediction = get_object_or_404(Prediction, pk=pk, user=request.user)

    context = {
        'prediction': prediction,
        'quantum_result': json.dumps(prediction.quantum_result, indent=2),
        'classical_result': json.dumps(prediction.classical_result, indent=2),
        'final_prediction': json.dumps(prediction.final_prediction, indent=2),
    }
    return render(request, 'predictor/prediction_detail.html', context)


@login_required
def topic_analysis(request):
    """Display topic frequency analysis across all exam papers."""
    topics = Topic.objects.filter(exam_paper__user=request.user).order_by('-frequency')[:20]

    # Prepare data for charts
    topic_names = [topic.name for topic in topics]
    topic_frequencies = [topic.frequency for topic in topics]

    context = {
        'topics': topics,
        'topic_names_json': json.dumps(topic_names),
        'topic_frequencies_json': json.dumps(topic_frequencies),
    }
    return render(request, 'predictor/topic_analysis.html', context)


@login_required
@require_POST
def exam_process(request, pk):
    """Process an uploaded exam paper for analysis."""
    try:
        exam_paper = get_object_or_404(ExamPaper, pk=pk, user=request.user)

        # Import exam analysis service
        from .services.exam_analysis_service import ExamAnalysisService

        # Initialize analysis service
        analysis_service = ExamAnalysisService()

        # Read exam file content
        with exam_paper.file.open('rb') as f:
            file_content = f.read()

        # Analyze the exam
        result = analysis_service.analyze_exam_file(
            file_content=file_content,
            filename=exam_paper.file.name
        )

        if result.success:
            # Update exam paper with analysis results
            exam_paper.questions_data = result.topic_breakdown.get('question_details', [])
            exam_paper.topics_covered = list(result.topic_breakdown.get('topics', {}).keys())
            exam_paper.analysis_data = {
                'topic_breakdown': result.topic_breakdown,
                'frequency_analysis': result.frequency_analysis,
                'predictions': result.predictions,
                'processing_stats': result.processing_stats
            }
            exam_paper.processed = True
            exam_paper.processed_at = timezone.now()
            exam_paper.save()

            return JsonResponse({
                'status': 'success',
                'message': f'Exam analyzed successfully. Found {result.total_questions} questions.',
                'analysis_data': {
                    'total_questions': result.total_questions,
                    'topics_found': len(result.topic_breakdown.get('topics', {})),
                    'processing_time': result.processing_stats.get('total_processing_time', 0),
                    'success_rate': result.processing_stats.get('success_rate', 0)
                }
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Analysis failed: {result.error}'
            })

    except ImportError as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Missing dependencies: {e}. Please install required packages.'
        })
    except Exception as e:
        logger.error(f"Error processing exam {pk}: {e}")
        return JsonResponse({
            'status': 'error',
            'message': f'Processing failed: {str(e)}'
        })


@login_required
def exam_analysis(request, pk):
    """Display detailed exam analysis results."""
    exam_paper = get_object_or_404(ExamPaper, pk=pk, user=request.user)

    if not exam_paper.processed or not exam_paper.analysis_data:
        messages.warning(request, 'Exam has not been analyzed yet. Please process it first.')
        return redirect('predictor:exam_detail', pk=pk)

    # Prepare analysis data for template
    analysis_data = exam_paper.analysis_data
    topic_breakdown = analysis_data.get('topic_breakdown', {})
    frequency_analysis = analysis_data.get('frequency_analysis', {})
    predictions = analysis_data.get('predictions', {})

    # Prepare chart data
    topics = topic_breakdown.get('topics', {})
    topic_names = list(topics.keys())
    topic_frequencies = [data.get('percentage', 0) for data in topics.values()]

    context = {
        'exam_paper': exam_paper,
        'topic_breakdown': topic_breakdown,
        'frequency_analysis': frequency_analysis,
        'predictions': predictions,
        'topic_names_json': json.dumps(topic_names),
        'topic_frequencies_json': json.dumps(topic_frequencies),
        'question_details': topic_breakdown.get('question_details', []),
    }

    return render(request, 'predictor/exam_analysis.html', context)


@login_required
def dashboard_data_api(request):
    """API endpoint for real-time dashboard data."""
    try:
        # Get topic data
        topics = Topic.objects.filter(exam_paper__user=request.user).order_by('-frequency')[:20]

        # Prepare response data
        data = {
            'total_exams': ExamPaper.objects.filter(user=request.user).count(),
            'total_topics': topics.count(),
            'total_predictions': Prediction.objects.filter(user=request.user).count(),
            'topic_names': [topic.name for topic in topics],
            'topic_frequencies': [topic.frequency for topic in topics],
            'topics_data': []
        }

        # Add detailed topic information
        for topic in topics:
            topic_data = {
                'id': topic.id,
                'name': topic.name,
                'frequency': topic.frequency,
                'description': topic.description,
                'category': topic.metadata.get('category', 'N/A') if topic.metadata else 'N/A',
                'exam_paper_title': topic.exam_paper.title,
                'confidence': topic.metadata.get('confidence', 0) if topic.metadata else 0
            }
            data['topics_data'].append(topic_data)

        return JsonResponse(data)

    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# Authentication API Views
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token


@csrf_exempt
@require_POST
def api_login(request):
    """API endpoint for user login."""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return JsonResponse({
                'success': False,
                'message': 'Username and password are required'
            }, status=400)

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            
            # For now, return a simple token (in production, use proper JWT)
            token = f"session_{user.id}_{user.username}"
            
            return JsonResponse({
                'success': True,
                'message': 'Login successful',
                'token': token,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Invalid credentials'
            }, status=401)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Login error: {e}")
        return JsonResponse({
            'success': False,
            'message': 'Internal server error'
        }, status=500)


@csrf_exempt
def api_register(request):
    """API endpoint for user registration."""
    try:
        logger.info(f"Registration request received. Method: {request.method}")
        
        if request.method != 'POST':
            return JsonResponse({
                'success': False,
                'message': 'Only POST method is allowed'
            }, status=405)
            
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Request body: {request.body.decode('utf-8')}")
        
        data = json.loads(request.body)
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')

        logger.info(f"Parsed data - username: {username}, email: {email}, password: {'[HIDDEN]' if password else None}")

        if not username or not email or not password:
            logger.warning("Missing required fields")
            return JsonResponse({
                'success': False,
                'message': 'Username, email, and password are required'
            }, status=400)

        # Check if user already exists
        logger.info("Checking if username already exists...")
        if User.objects.filter(username=username).exists():
            logger.warning(f"Username {username} already exists")
            return JsonResponse({
                'success': False,
                'message': 'Username already exists'
            }, status=400)

        logger.info("Checking if email already exists...")
        if User.objects.filter(email=email).exists():
            logger.warning(f"Email {email} already exists")
            return JsonResponse({
                'success': False,
                'message': 'Email already exists'
            }, status=400)

        # Create user
        logger.info("Creating new user...")
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        logger.info(f"User created successfully with ID: {user.id}")

        # Log the user in
        logger.info("Logging in user...")
        login(request, user)
        logger.info("User logged in successfully")

        # For now, return a simple token (in production, use proper JWT)
        # This is a simple session-based approach
        token = f"session_{user.id}_{user.username}"

        return JsonResponse({
            'success': True,
            'message': 'Registration successful',
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
        })

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Registration error: {e}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }, status=500)


def api_logout(request):
    """API endpoint for user logout."""
    logout(request)
    return JsonResponse({
        'success': True,
        'message': 'Logout successful'
    })


@login_required
def api_validate_token(request):
    """API endpoint to validate user session/token."""
    user = request.user
    return JsonResponse({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        }
    })


def api_csrf_token(request):
    """API endpoint to get CSRF token."""
    return JsonResponse({
        'csrf_token': get_token(request)
    })
