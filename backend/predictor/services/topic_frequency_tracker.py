"""Topic frequency tracking and prediction service."""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import statistics

from django.db import models
from django.utils import timezone

from .question_classifier import TopicClassification

logger = logging.getLogger(__name__)


@dataclass
class TopicFrequency:
    """Frequency data for a topic."""
    topic: str
    total_questions: int
    frequency_percentage: float
    trend_direction: str  # 'increasing', 'decreasing', 'stable'
    confidence_score: float
    last_seen: datetime
    prediction_weight: float


@dataclass
class FrequencyAnalysis:
    """Analysis of topic frequencies across exams."""
    success: bool
    topic_frequencies: List[TopicFrequency]
    trend_analysis: Dict[str, Any]
    predictions: Dict[str, Any]
    error: Optional[str] = None


class TopicFrequencyTracker:
    """Service for tracking and predicting topic frequencies."""

    def __init__(self):
        """Initialize frequency tracker."""
        self.min_samples = 3  # Minimum exams needed for trend analysis
        self.prediction_horizon = 12  # Months to predict ahead
        logger.info("TopicFrequencyTracker initialized")

    def analyze_frequencies(self, classifications: List[TopicClassification],
                          exam_history: Optional[List[Dict[str, Any]]] = None) -> FrequencyAnalysis:
        """
        Analyze topic frequencies and predict future trends.

        Args:
            classifications: Current exam classifications
            exam_history: Historical exam data for trend analysis

        Returns:
            FrequencyAnalysis with trends and predictions
        """
        try:
            # Calculate current frequencies
            current_frequencies = self._calculate_current_frequencies(classifications)

            # Analyze trends if historical data available
            trend_analysis = {}
            if exam_history and len(exam_history) >= self.min_samples:
                trend_analysis = self._analyze_trends(current_frequencies, exam_history)

            # Generate predictions
            predictions = self._generate_predictions(current_frequencies, trend_analysis)

            # Create frequency objects
            topic_frequencies = []
            for topic, data in current_frequencies.items():
                trend = trend_analysis.get(topic, {}).get('direction', 'stable')
                confidence = trend_analysis.get(topic, {}).get('confidence', 0.5)
                prediction_weight = predictions.get(topic, {}).get('weight', 0.5)

                frequency = TopicFrequency(
                    topic=topic,
                    total_questions=data['count'],
                    frequency_percentage=data['percentage'],
                    trend_direction=trend,
                    confidence_score=confidence,
                    last_seen=timezone.now(),
                    prediction_weight=prediction_weight
                )
                topic_frequencies.append(frequency)

            logger.info(f"Analyzed frequencies for {len(topic_frequencies)} topics")

            return FrequencyAnalysis(
                success=True,
                topic_frequencies=topic_frequencies,
                trend_analysis=trend_analysis,
                predictions=predictions
            )

        except Exception as e:
            logger.error(f"Error analyzing frequencies: {e}")
            return FrequencyAnalysis(
                success=False,
                topic_frequencies=[],
                trend_analysis={},
                predictions={},
                error=str(e)
            )

    def _calculate_current_frequencies(self, classifications: List[TopicClassification]) -> Dict[str, Dict[str, Any]]:
        """Calculate frequency distribution for current classifications."""
        total_questions = len(classifications)
        if total_questions == 0:
            return {}

        frequency_map = {}

        for classification in classifications:
            topic = classification.primary_topic

            if topic not in frequency_map:
                frequency_map[topic] = {
                    'count': 0,
                    'total_confidence': 0.0,
                    'secondary_topics': {},
                    'academic_levels': {}
                }

            data = frequency_map[topic]
            data['count'] += 1
            data['total_confidence'] += classification.confidence

            # Track secondary topics
            for secondary in classification.secondary_topics:
                data['secondary_topics'][secondary] = \
                    data['secondary_topics'].get(secondary, 0) + 1

            # Track academic levels
            level = classification.academic_level
            data['academic_levels'][level] = \
                data['academic_levels'].get(level, 0) + 1

        # Calculate percentages and averages
        for topic, data in frequency_map.items():
            data['percentage'] = (data['count'] / total_questions) * 100
            data['avg_confidence'] = data['total_confidence'] / data['count']

        return frequency_map

    def _analyze_trends(self, current_frequencies: Dict[str, Dict[str, Any]],
                       exam_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze trends across historical exam data."""
        trend_analysis = {}

        for topic in current_frequencies.keys():
            topic_trends = []

            # Extract historical frequencies for this topic
            for exam in exam_history:
                exam_topics = exam.get('topics', {})
                if topic in exam_topics:
                    topic_data = exam_topics[topic]
                    topic_trends.append({
                        'date': exam.get('date', datetime.now()),
                        'frequency': topic_data.get('percentage', 0),
                        'questions': topic_data.get('count', 0)
                    })

            if len(topic_trends) >= 2:
                # Calculate trend direction
                frequencies = [t['frequency'] for t in topic_trends]
                direction = self._calculate_trend_direction(frequencies)

                # Calculate confidence in trend
                confidence = self._calculate_trend_confidence(frequencies)

                trend_analysis[topic] = {
                    'direction': direction,
                    'confidence': confidence,
                    'historical_data': topic_trends,
                    'slope': self._calculate_slope(frequencies),
                    'volatility': self._calculate_volatility(frequencies)
                }
            else:
                trend_analysis[topic] = {
                    'direction': 'stable',
                    'confidence': 0.5,
                    'historical_data': topic_trends,
                    'slope': 0.0,
                    'volatility': 0.0
                }

        return trend_analysis

    def _calculate_trend_direction(self, frequencies: List[float]) -> str:
        """Calculate trend direction from frequency data."""
        if len(frequencies) < 2:
            return 'stable'

        # Simple linear trend
        n = len(frequencies)
        x = list(range(n))
        slope = self._calculate_slope(frequencies)

        if slope > 0.5:
            return 'increasing'
        elif slope < -0.5:
            return 'decreasing'
        else:
            return 'stable'

    def _calculate_slope(self, values: List[float]) -> float:
        """Calculate slope of linear trend."""
        if len(values) < 2:
            return 0.0

        n = len(values)
        x_mean = sum(range(n)) / n
        y_mean = sum(values) / n

        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        return numerator / denominator if denominator != 0 else 0.0

    def _calculate_trend_confidence(self, frequencies: List[float]) -> float:
        """Calculate confidence in trend direction."""
        if len(frequencies) < 3:
            return 0.5

        # Use coefficient of determination (R²) as confidence measure
        slope = self._calculate_slope(frequencies)
        n = len(frequencies)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(frequencies) / n

        # Calculate R²
        ss_res = sum((frequencies[i] - (slope * i + (y_mean - slope * x_mean))) ** 2 for i in range(n))
        ss_tot = sum((y - y_mean) ** 2 for y in frequencies)

        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

        return min(r_squared, 1.0)  # Cap at 1.0

    def _calculate_volatility(self, values: List[float]) -> float:
        """Calculate volatility (standard deviation) of frequency data."""
        if len(values) < 2:
            return 0.0

        try:
            return statistics.stdev(values)
        except statistics.StatisticsError:
            return 0.0

    def _generate_predictions(self, current_frequencies: Dict[str, Dict[str, Any]],
                            trend_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate predictions for future topic frequencies."""
        predictions = {}

        for topic, current_data in current_frequencies.items():
            trend_data = trend_analysis.get(topic, {})
            slope = trend_data.get('slope', 0.0)
            volatility = trend_data.get('volatility', 0.0)

            # Predict future frequency
            current_freq = current_data['percentage']
            predicted_freq = current_freq + (slope * self.prediction_horizon)

            # Ensure prediction is within reasonable bounds
            predicted_freq = max(0, min(100, predicted_freq))

            # Calculate prediction weight based on confidence and volatility
            confidence = trend_data.get('confidence', 0.5)
            volatility_penalty = max(0, 1 - (volatility / 10))  # Penalize high volatility
            prediction_weight = confidence * volatility_penalty

            predictions[topic] = {
                'current_frequency': current_freq,
                'predicted_frequency': predicted_freq,
                'change_percentage': ((predicted_freq - current_freq) / current_freq * 100) if current_freq > 0 else 0,
                'weight': prediction_weight,
                'confidence': confidence,
                'volatility': volatility
            }

        return predictions

    def get_top_predicted_topics(self, predictions: Dict[str, Any], top_n: int = 10) -> List[Dict[str, Any]]:
        """Get top predicted topics by importance."""
        topic_list = []

        for topic, data in predictions.items():
            importance_score = data['weight'] * data['predicted_frequency']
            topic_list.append({
                'topic': topic,
                'importance_score': importance_score,
                'predicted_frequency': data['predicted_frequency'],
                'change_percentage': data['change_percentage'],
                'weight': data['weight']
            })

        # Sort by importance score
        topic_list.sort(key=lambda x: x['importance_score'], reverse=True)

        return topic_list[:top_n]

    def generate_frequency_report(self, analysis: FrequencyAnalysis) -> Dict[str, Any]:
        """Generate a comprehensive frequency analysis report."""
        report = {
            'summary': {
                'total_topics': len(analysis.topic_frequencies),
                'total_questions': sum(f.total_questions for f in analysis.topic_frequencies),
                'generated_at': timezone.now().isoformat(),
                'analysis_period': f"{self.prediction_horizon} months"
            },
            'topic_breakdown': [],
            'trend_summary': {
                'increasing': 0,
                'decreasing': 0,
                'stable': 0
            },
            'predictions': {
                'top_rising_topics': [],
                'top_declining_topics': [],
                'high_confidence_predictions': []
            }
        }

        # Topic breakdown
        for freq in analysis.topic_frequencies:
            topic_data = {
                'topic': freq.topic,
                'frequency_percentage': freq.frequency_percentage,
                'trend': freq.trend_direction,
                'confidence': freq.confidence_score,
                'prediction_weight': freq.prediction_weight
            }
            report['topic_breakdown'].append(topic_data)

            # Update trend summary
            report['trend_summary'][freq.trend_direction] += 1

        # Sort topic breakdown by frequency
        report['topic_breakdown'].sort(key=lambda x: x['frequency_percentage'], reverse=True)

        # Generate prediction insights
        if analysis.predictions:
            rising_topics = []
            declining_topics = []
            high_confidence = []

            for topic, pred_data in analysis.predictions.items():
                change = pred_data['change_percentage']

                if change > 5:  # Rising topics
                    rising_topics.append({
                        'topic': topic,
                        'change': change,
                        'predicted_freq': pred_data['predicted_frequency']
                    })
                elif change < -5:  # Declining topics
                    declining_topics.append({
                        'topic': topic,
                        'change': change,
                        'predicted_freq': pred_data['predicted_frequency']
                    })

                if pred_data['weight'] > 0.7:  # High confidence predictions
                    high_confidence.append({
                        'topic': topic,
                        'weight': pred_data['weight'],
                        'predicted_freq': pred_data['predicted_frequency']
                    })

            report['predictions']['top_rising_topics'] = sorted(rising_topics, key=lambda x: x['change'], reverse=True)[:5]
            report['predictions']['top_declining_topics'] = sorted(declining_topics, key=lambda x: abs(x['change']), reverse=True)[:5]
            report['predictions']['high_confidence_predictions'] = sorted(high_confidence, key=lambda x: x['weight'], reverse=True)[:5]

        return report
