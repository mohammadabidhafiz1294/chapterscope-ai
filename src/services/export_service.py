"""Export service for generating PDF, CSV, and JSON reports."""

import csv
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.config import service_logger
from src.models import Report, ReportData, Visualization


class ExportService:
    """Service for exporting reports in various formats."""

    def __init__(self, export_dir: str = "data/exports"):
        """Initialize export service."""
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        service_logger.info("ExportService initialized", export_dir=str(export_dir))

    def export_pdf(self, report: Report, data: List[ReportData],
                   visualizations: List[Visualization]) -> str:
        """
        Export report as PDF.

        Args:
            report: Report object
            data: List of report data
            visualizations: List of visualizations

        Returns:
            Path to generated PDF file
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.platypus.flowables import Image
        except ImportError:
            raise RuntimeError("ReportLab not installed. Install with: pip install reportlab")

        service_logger.info("Starting PDF export", report_id=report.id)

        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{report.id}_{timestamp}.pdf"
        filepath = self.export_dir / filename

        # Create PDF document
        doc = SimpleDocTemplate(str(filepath), pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
        )
        story.append(Paragraph(report.title, title_style))
        story.append(Spacer(1, 12))

        # Description
        if report.description:
            story.append(Paragraph(report.description, styles['Normal']))
            story.append(Spacer(1, 12))

        # Metadata
        metadata_style = ParagraphStyle(
            'Metadata',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.gray,
        )
        metadata = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>"
        metadata += f"Topics: {', '.join(report.topics)}<br/>"
        metadata += f"Prediction Year: {report.prediction_year or 'N/A'}<br/>"
        metadata += f"Confidence Threshold: {report.confidence_threshold}"
        story.append(Paragraph(metadata, metadata_style))
        story.append(Spacer(1, 24))

        # Results table
        if data:
            story.append(Paragraph("Prediction Results", styles['Heading2']))
            story.append(Spacer(1, 12))

            # Table headers
            headers = ['Topic', 'Prediction Score', 'Confidence', 'Trend', 'Quantum Contribution']

            # Table data
            table_data = [headers]
            for item in data:
                row = [
                    item.topic,
                    ".4f",
                    ".4f",
                    item.trend.title(),
                    ".1f"
                ]
                table_data.append(row)

            # Create table
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            story.append(table)
            story.append(Spacer(1, 24))

        # Historical data section
        if data and data[0].historical_data:
            story.append(Paragraph("Historical Data", styles['Heading2']))
            story.append(Spacer(1, 12))

            for item in data[:3]:  # Show first 3 topics
                story.append(Paragraph(f"Topic: {item.topic}", styles['Heading3']))
                story.append(Spacer(1, 6))

                hist_headers = ['Year', 'Frequency %']
                hist_data = [hist_headers]

                for hist in item.historical_data[-5:]:  # Last 5 years
                    hist_data.append([str(hist['year']), ".2f"])

                hist_table = Table(hist_data)
                hist_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))

                story.append(hist_table)
                story.append(Spacer(1, 12))

        # Build PDF
        doc.build(story)

        service_logger.info("PDF export completed", filepath=str(filepath))
        return str(filepath)

    def export_csv(self, report: Report, data: List[ReportData]) -> str:
        """
        Export report data as CSV.

        Args:
            report: Report object
            data: List of report data

        Returns:
            Path to generated CSV file
        """
        service_logger.info("Starting CSV export", report_id=report.id)

        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{report.id}_{timestamp}.csv"
        filepath = self.export_dir / filename

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'topic', 'prediction_score', 'confidence', 'trend',
                'quantum_contribution', 'classical_contribution'
            ]

            # Add historical data columns
            max_hist_years = 0
            if data:
                for item in data:
                    if item.historical_data:
                        max_hist_years = max(max_hist_years, len(item.historical_data))

            for i in range(max_hist_years):
                fieldnames.extend([f'hist_year_{i+1}', f'hist_freq_{i+1}'])

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for item in data:
                row = {
                    'topic': item.topic,
                    'prediction_score': item.prediction_score,
                    'confidence': item.confidence,
                    'trend': item.trend,
                    'quantum_contribution': item.quantum_contribution,
                    'classical_contribution': item.classical_contribution
                }

                # Add historical data
                if item.historical_data:
                    for i, hist in enumerate(item.historical_data):
                        row[f'hist_year_{i+1}'] = hist['year']
                        row[f'hist_freq_{i+1}'] = hist['percentage']

                writer.writerow(row)

        service_logger.info("CSV export completed", filepath=str(filepath))
        return str(filepath)

    def export_json(self, report: Report, data: List[ReportData],
                    visualizations: List[Visualization]) -> str:
        """
        Export report as JSON.

        Args:
            report: Report object
            data: List of report data
            visualizations: List of visualizations

        Returns:
            Path to generated JSON file
        """
        service_logger.info("Starting JSON export", report_id=report.id)

        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{report.id}_{timestamp}.json"
        filepath = self.export_dir / filename

        # Build JSON structure
        export_data = {
            "report": {
                "id": report.id,
                "title": report.title,
                "description": report.description,
                "topics": report.topics,
                "status": report.status,
                "prediction_year": report.prediction_year,
                "confidence_threshold": report.confidence_threshold,
                "created_at": report.created_at.isoformat(),
                "updated_at": report.updated_at.isoformat()
            },
            "predictions": [
                {
                    "topic": item.topic,
                    "prediction_score": item.prediction_score,
                    "confidence": item.confidence,
                    "trend": item.trend,
                    "quantum_contribution": item.quantum_contribution,
                    "classical_contribution": item.classical_contribution,
                    "historical_data": item.historical_data
                }
                for item in data
            ],
            "visualizations": [
                {
                    "id": viz.id,
                    "type": viz.type,
                    "title": viz.title,
                    "data": viz.data,
                    "config": viz.config
                }
                for viz in visualizations
            ],
            "export_metadata": {
                "exported_at": datetime.now().isoformat(),
                "format": "json",
                "version": "1.0"
            }
        }

        with open(filepath, 'w', encoding='utf-8') as jsonfile:
            json.dump(export_data, jsonfile, indent=2, ensure_ascii=False)

        service_logger.info("JSON export completed", filepath=str(filepath))
        return str(filepath)

    def cleanup_old_exports(self, max_age_days: int = 7) -> int:
        """
        Clean up old export files.

        Args:
            max_age_days: Maximum age of files to keep

        Returns:
            Number of files deleted
        """
        import time

        service_logger.info("Starting export cleanup", max_age_days=max_age_days)

        deleted_count = 0
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

        for filepath in self.export_dir.glob("*.pdf"):
            if filepath.stat().st_mtime < cutoff_time:
                filepath.unlink()
                deleted_count += 1

        for filepath in self.export_dir.glob("*.csv"):
            if filepath.stat().st_mtime < cutoff_time:
                filepath.unlink()
                deleted_count += 1

        for filepath in self.export_dir.glob("*.json"):
            if filepath.stat().st_mtime < cutoff_time:
                filepath.unlink()
                deleted_count += 1

        if deleted_count > 0:
            service_logger.info("Export cleanup completed", deleted_count=deleted_count)

        return deleted_count
