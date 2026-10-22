"""
Predictor services package.

This package contains various services for the EduQuantum predictor system:
- EduQuantum Integrator: Main service orchestrator
- Exam Analysis Service: Analyze exam papers and extract topics
- Quantum Prediction Engine: Quantum-based prediction algorithms
- Gemini Client: Interface with Google's Gemini AI
- Question Classifier: Classify questions by topic
- Question Segmenter: Segment exam papers into individual questions
- Topic Extractor: Extract topics from text content
- Topic Frequency Tracker: Track topic frequencies over time
- Quantum Circuit Constructor: Build quantum circuits for VQE
"""

from .eduquantum_integrator import EduQuantumIntegrator
from .exam_analysis_service import ExamAnalysisService
from .quantum_prediction_engine import QuantumPredictionEngine
from .gemini_client import GeminiClient

__all__ = [
    'EduQuantumIntegrator',
    'ExamAnalysisService', 
    'QuantumPredictionEngine',
    'GeminiClient',
]