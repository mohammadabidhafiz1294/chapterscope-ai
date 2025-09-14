"""Visualization service for generating Chart.js compatible visualizations."""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.config import service_logger
from src.models import Report, ReportData, Visualization


class VisualizationService:
    """Service for generating data visualizations."""

    def __init__(self):
        """Initialize visualization service."""
        service_logger.info("VisualizationService initialized")

    def generate_visualizations(self, report: Report, data: List[ReportData]) -> List[Visualization]:
        """
        Generate all visualizations for a report.

        Args:
            report: Report object
            data: List of report data

        Returns:
            List of generated visualizations
        """
        if not data:
            service_logger.warning("No data available for visualization generation")
            return []

        visualizations = []

        # Generate bar chart for prediction scores
        bar_chart = self._generate_prediction_scores_chart(report, data)
        if bar_chart:
            visualizations.append(bar_chart)

        # Generate trend chart
        trend_chart = self._generate_trend_chart(report, data)
        if trend_chart:
            visualizations.append(trend_chart)

        # Generate confidence interval chart
        confidence_chart = self._generate_confidence_chart(report, data)
        if confidence_chart:
            visualizations.append(confidence_chart)

        # Generate historical trends chart
        historical_chart = self._generate_historical_trends_chart(report, data)
        if historical_chart:
            visualizations.append(historical_chart)

        # Generate topic comparison chart
        comparison_chart = self._generate_topic_comparison_chart(report, data)
        if comparison_chart:
            visualizations.append(comparison_chart)

        service_logger.info("Visualizations generated",
                          report_id=report.id,
                          count=len(visualizations))

        return visualizations

    def _generate_prediction_scores_chart(self, report: Report, data: List[ReportData]) -> Optional[Visualization]:
        """Generate bar chart for prediction scores."""
        if not data:
            return None

        # Prepare data for Chart.js
        labels = [item.topic.replace('_', ' ').title() for item in data]
        scores = [item.prediction_score for item in data]

        chart_data = {
            "labels": labels,
            "datasets": [{
                "label": "Prediction Score",
                "data": scores,
                "backgroundColor": [
                    "rgba(54, 162, 235, 0.8)",
                    "rgba(255, 99, 132, 0.8)",
                    "rgba(75, 192, 192, 0.8)",
                    "rgba(255, 205, 86, 0.8)",
                    "rgba(153, 102, 255, 0.8)",
                    "rgba(255, 159, 64, 0.8)"
                ],
                "borderColor": [
                    "rgba(54, 162, 235, 1)",
                    "rgba(255, 99, 132, 1)",
                    "rgba(75, 192, 192, 1)",
                    "rgba(255, 205, 86, 1)",
                    "rgba(153, 102, 255, 1)",
                    "rgba(255, 159, 64, 1)"
                ],
                "borderWidth": 2
            }]
        }

        config = {
            "type": "bar",
            "data": chart_data,
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Topic Prediction Scores",
                        "font": {"size": 16}
                    },
                    "legend": {
                        "display": True,
                        "position": "top"
                    },
                    "tooltip": {
                        "callbacks": {
                            "label": "function(context) { return context.label + ': ' + (context.parsed.y * 100).toFixed(1) + '%'; }"
                        }
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "max": 1.0,
                        "ticks": {
                            "callback": "function(value) { return (value * 100) + '%'; }"
                        }
                    },
                    "x": {
                        "ticks": {
                            "maxRotation": 45,
                            "minRotation": 45
                        }
                    }
                },
                "accessibility": {
                    "enabled": True,
                    "description": "Bar chart showing prediction scores for different topics"
                }
            }
        }

        return Visualization.create(
            report_id=report.id,
            type="bar",
            title="Topic Prediction Scores",
            data=chart_data,
            config=config
        )

    def _generate_trend_chart(self, report: Report, data: List[ReportData]) -> Optional[Visualization]:
        """Generate line chart for topic trends."""
        if not data:
            return None

        # Map trends to numerical values
        trend_map = {
            "increasing": 1,
            "stable": 0,
            "decreasing": -1
        }

        labels = [item.topic.replace('_', ' ').title() for item in data]
        trend_values = [trend_map.get(item.trend, 0) for item in data]

        chart_data = {
            "labels": labels,
            "datasets": [{
                "label": "Trend Direction",
                "data": trend_values,
                "borderColor": "rgba(255, 99, 132, 1)",
                "backgroundColor": "rgba(255, 99, 132, 0.1)",
                "borderWidth": 3,
                "fill": True,
                "tension": 0.4,
                "pointBackgroundColor": [
                    "rgba(255, 99, 132, 1)",
                    "rgba(54, 162, 235, 1)",
                    "rgba(75, 192, 192, 1)"
                ],
                "pointBorderColor": "#fff",
                "pointBorderWidth": 2,
                "pointRadius": 8
            }]
        }

        config = {
            "type": "line",
            "data": chart_data,
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Topic Trend Analysis",
                        "font": {"size": 16}
                    },
                    "legend": {
                        "display": True,
                        "position": "top"
                    },
                    "tooltip": {
                        "callbacks": {
                            "label": "function(context) { var trends = ['Decreasing', 'Stable', 'Increasing']; return context.label + ': ' + trends[context.parsed.y + 1]; }"
                        }
                    }
                },
                "scales": {
                    "y": {
                        "min": -1,
                        "max": 1,
                        "ticks": {
                            "callback": "function(value) { var trends = ['Decreasing', 'Stable', 'Increasing']; return trends[value + 1]; }"
                        }
                    },
                    "x": {
                        "ticks": {
                            "maxRotation": 45,
                            "minRotation": 45
                        }
                    }
                },
                "accessibility": {
                    "enabled": True,
                    "description": "Line chart showing trend directions for different topics"
                }
            }
        }

        return Visualization.create(
            report_id=report.id,
            type="line",
            title="Topic Trend Analysis",
            data=chart_data,
            config=config
        )

    def _generate_confidence_chart(self, report: Report, data: List[ReportData]) -> Optional[Visualization]:
        """Generate confidence interval visualization."""
        if not data:
            return None

        labels = [item.topic.replace('_', ' ').title() for item in data]
        scores = [item.prediction_score for item in data]
        confidences = [item.confidence for item in data]

        chart_data = {
            "labels": labels,
            "datasets": [
                {
                    "label": "Prediction Score",
                    "data": scores,
                    "backgroundColor": "rgba(54, 162, 235, 0.8)",
                    "borderColor": "rgba(54, 162, 235, 1)",
                    "borderWidth": 2,
                    "type": "bar"
                },
                {
                    "label": "Confidence Range",
                    "data": confidences,
                    "backgroundColor": "rgba(255, 99, 132, 0.3)",
                    "borderColor": "rgba(255, 99, 132, 1)",
                    "borderWidth": 2,
                    "type": "line",
                    "fill": False,
                    "tension": 0.4
                }
            ]
        }

        config = {
            "type": "bar",
            "data": chart_data,
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Prediction Scores with Confidence",
                        "font": {"size": 16}
                    },
                    "legend": {
                        "display": True,
                        "position": "top"
                    },
                    "tooltip": {
                        "callbacks": {
                            "label": "function(context) { return context.dataset.label + ': ' + (context.parsed.y * 100).toFixed(1) + '%'; }"
                        }
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "max": 1.0,
                        "ticks": {
                            "callback": "function(value) { return (value * 100) + '%'; }"
                        }
                    },
                    "x": {
                        "ticks": {
                            "maxRotation": 45,
                            "minRotation": 45
                        }
                    }
                },
                "accessibility": {
                    "enabled": True,
                    "description": "Combined bar and line chart showing prediction scores and confidence ranges"
                }
            }
        }

        return Visualization.create(
            report_id=report.id,
            type="combo",
            title="Prediction Scores with Confidence",
            data=chart_data,
            config=config
        )

    def _generate_historical_trends_chart(self, report: Report, data: List[ReportData]) -> Optional[Visualization]:
        """Generate historical trends visualization."""
        if not data or not data[0].historical_data:
            return None

        # Get years from first topic's historical data
        years = []
        if data[0].historical_data:
            years = [str(hist['year']) for hist in data[0].historical_data]

        datasets = []
        colors = [
            "rgba(54, 162, 235, 1)",
            "rgba(255, 99, 132, 1)",
            "rgba(75, 192, 192, 1)",
            "rgba(255, 205, 86, 1)",
            "rgba(153, 102, 255, 1)"
        ]

        for i, item in enumerate(data[:5]):  # Show up to 5 topics
            if item.historical_data:
                frequencies = [hist['percentage'] for hist in item.historical_data]
                datasets.append({
                    "label": item.topic.replace('_', ' ').title(),
                    "data": frequencies,
                    "borderColor": colors[i % len(colors)],
                    "backgroundColor": colors[i % len(colors)].replace("1)", "0.1)"),
                    "borderWidth": 2,
                    "fill": False,
                    "tension": 0.4
                })

        if not datasets:
            return None

        chart_data = {
            "labels": years,
            "datasets": datasets
        }

        config = {
            "type": "line",
            "data": chart_data,
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Historical Frequency Trends",
                        "font": {"size": 16}
                    },
                    "legend": {
                        "display": True,
                        "position": "top"
                    },
                    "tooltip": {
                        "callbacks": {
                            "label": "function(context) { return context.dataset.label + ': ' + context.parsed.y.toFixed(1) + '%'; }"
                        }
                    }
                },
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "ticks": {
                            "callback": "function(value) { return value + '%'; }"
                        }
                    },
                    "x": {
                        "title": {
                            "display": True,
                            "text": "Year"
                        }
                    }
                },
                "accessibility": {
                    "enabled": True,
                    "description": "Line chart showing historical frequency trends for different topics over time"
                }
            }
        }

        return Visualization.create(
            report_id=report.id,
            type="line",
            title="Historical Frequency Trends",
            data=chart_data,
            config=config
        )

    def _generate_topic_comparison_chart(self, report: Report, data: List[ReportData]) -> Optional[Visualization]:
        """Generate topic comparison radar chart."""
        if len(data) < 3:  # Need at least 3 topics for meaningful radar
            return None

        labels = [item.topic.replace('_', ' ').title() for item in data]
        scores = [item.prediction_score for item in data]

        chart_data = {
            "labels": labels,
            "datasets": [{
                "label": "Prediction Scores",
                "data": scores,
                "backgroundColor": "rgba(54, 162, 235, 0.2)",
                "borderColor": "rgba(54, 162, 235, 1)",
                "borderWidth": 2,
                "pointBackgroundColor": "rgba(54, 162, 235, 1)",
                "pointBorderColor": "#fff",
                "pointBorderWidth": 2,
                "pointRadius": 6
            }]
        }

        config = {
            "type": "radar",
            "data": chart_data,
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Topic Comparison",
                        "font": {"size": 16}
                    },
                    "legend": {
                        "display": True,
                        "position": "top"
                    },
                    "tooltip": {
                        "callbacks": {
                            "label": "function(context) { return context.label + ': ' + (context.parsed.r * 100).toFixed(1) + '%'; }"
                        }
                    }
                },
                "scales": {
                    "r": {
                        "beginAtZero": True,
                        "max": 1.0,
                        "ticks": {
                            "callback": "function(value) { return (value * 100) + '%'; }"
                        },
                        "grid": {
                            "color": "rgba(0, 0, 0, 0.1)"
                        },
                        "angleLines": {
                            "color": "rgba(0, 0, 0, 0.1)"
                        },
                        "pointLabels": {
                            "font": {"size": 12}
                        }
                    }
                },
                "accessibility": {
                    "enabled": True,
                    "description": "Radar chart comparing prediction scores across different topics"
                }
            }
        }

        return Visualization.create(
            report_id=report.id,
            type="radar",
            title="Topic Comparison",
            data=chart_data,
            config=config
        )
