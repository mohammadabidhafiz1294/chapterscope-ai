"""Report service for managing prediction reports and data operations."""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import uuid4

from sqlalchemy.orm import Session

from src.config import service_logger
from src.config.database import get_db_session
from src.models import (
    Report, ReportData, Visualization, ExportJob,
    ReportCreateRequest, ReportUpdateRequest,
    DBReport, DBReportData, DBVisualization, DBExportJob
)
from src.services.data_loader import DataLoader
from src.services.vqe_predictor import VQEPredictor
from src.services.export_service import ExportService
from src.services.visualization_service import VisualizationService


class ReportService:
    """Service for managing prediction reports and related operations."""

    def __init__(self, data_loader: Optional[DataLoader] = None,
                 vqe_predictor: Optional[VQEPredictor] = None,
                 visualization_service: Optional[VisualizationService] = None,
                 export_service: Optional[ExportService] = None):
        """Initialize report service."""
        self.data_loader = data_loader or DataLoader()
        self.vqe_predictor = vqe_predictor or VQEPredictor()
        self.visualization_service = visualization_service or VisualizationService()
        self.export_service = export_service or ExportService()

        # Create reports directory if it doesn't exist
        self.reports_dir = Path("data/reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        service_logger.info("ReportService initialized with database persistence")

    def create_report(self, request: ReportCreateRequest,
                     created_by: Optional[str] = None) -> Report:
        """Create a new report."""
        service_logger.info("Creating new report", title=request.title, topics=request.topics)

        report = Report.create(
            title=request.title,
            description=request.description,
            topics=request.topics,
            prediction_year=request.prediction_year,
            confidence_threshold=request.confidence_threshold,
            created_by=created_by
        )

        # Save to database
        db_session = get_db_session()
        try:
            db_report = DBReport(
                id=report.id,
                title=report.title,
                description=report.description,
                topics=report.topics,
                status=report.status,
                prediction_year=report.prediction_year,
                confidence_threshold=report.confidence_threshold,
                created_at=report.created_at,
                updated_at=report.updated_at,
                created_by=report.created_by,
                report_metadata=report.metadata
            )
            db_session.add(db_report)
            db_session.commit()
            service_logger.info("Report saved to database", report_id=report.id)
        except Exception as e:
            db_session.rollback()
            service_logger.error("Failed to save report to database", error=str(e))
            raise
        finally:
            db_session.close()

        service_logger.info("Report created successfully", report_id=report.id)
        return report

    def get_report(self, report_id: str) -> Optional[Report]:
        """Get a report by ID."""
        db_session = get_db_session()
        try:
            db_report = db_session.query(DBReport).filter(DBReport.id == report_id).first()
            if db_report:
                report = Report(
                    id=db_report.id,
                    title=db_report.title,
                    description=db_report.description,
                    topics=db_report.topics,
                    status=db_report.status,
                    prediction_year=db_report.prediction_year,
                    confidence_threshold=db_report.confidence_threshold,
                    created_at=db_report.created_at,
                    updated_at=db_report.updated_at,
                    created_by=db_report.created_by,
                    metadata=db_report.report_metadata
                )
                service_logger.debug("Report retrieved from database", report_id=report_id)
                return report
            else:
                service_logger.warning("Report not found in database", report_id=report_id)
                return None
        except Exception as e:
            service_logger.error("Failed to retrieve report from database", error=str(e))
            return None
        finally:
            db_session.close()

    def get_all_reports(
        self,
        page: int = 1,
        per_page: int = 10,
        status_filter: Optional[str] = None,
        prediction_year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get all reports with pagination and filtering."""
        db_session = get_db_session()
        try:
            query = db_session.query(DBReport)

            # Apply status filter
            if status_filter:
                query = query.filter(DBReport.status == status_filter)

            # Apply prediction year filter
            if prediction_year is not None:
                query = query.filter(DBReport.prediction_year == prediction_year)

            # Get total count
            total = query.count()

            # Sort by creation date (newest first)
            query = query.order_by(DBReport.created_at.desc())

            # Apply pagination
            start_idx = (page - 1) * per_page
            db_reports = query.offset(start_idx).limit(per_page).all()

            # Convert to Report objects
            reports = []
            for db_report in db_reports:
                report = Report(
                    id=db_report.id,
                    title=db_report.title,
                    description=db_report.description,
                    topics=db_report.topics,
                    status=db_report.status,
                    prediction_year=db_report.prediction_year,
                    confidence_threshold=db_report.confidence_threshold,
                    created_at=db_report.created_at,
                    updated_at=db_report.updated_at,
                    created_by=db_report.created_by,
                    metadata=db_report.report_metadata
                )
                reports.append(report)

            total_pages = (total + per_page - 1) // per_page

            service_logger.debug("Reports retrieved from database",
                               total=total, page=page, per_page=per_page,
                               status_filter=status_filter,
                               prediction_year=prediction_year)

            return {
                "items": reports,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": total_pages
            }
        except Exception as e:
            service_logger.error("Failed to retrieve reports from database", error=str(e))
            return {
                "items": [],
                "total": 0,
                "page": page,
                "per_page": per_page,
                "pages": 0
            }
        finally:
            db_session.close()

    def update_report(self, report_id: str, request: ReportUpdateRequest) -> Optional[Report]:
        """Update an existing report."""
        db_session = get_db_session()
        try:
            db_report = db_session.query(DBReport).filter(DBReport.id == report_id).first()
            if not db_report:
                service_logger.warning("Report not found in database for update", report_id=report_id)
                return None

            service_logger.info("Updating report in database", report_id=report_id)

            # Update fields if provided
            if request.title is not None:
                db_report.title = request.title
            if request.description is not None:
                db_report.description = request.description
            if request.topics is not None:
                db_report.topics = request.topics
            if request.prediction_year is not None:
                db_report.prediction_year = request.prediction_year
            if request.confidence_threshold is not None:
                db_report.confidence_threshold = request.confidence_threshold

            db_report.updated_at = datetime.now()
            db_session.commit()

            # Return updated report
            report = Report(
                id=db_report.id,
                title=db_report.title,
                description=db_report.description,
                topics=db_report.topics,
                status=db_report.status,
                prediction_year=db_report.prediction_year,
                confidence_threshold=db_report.confidence_threshold,
                created_at=db_report.created_at,
                updated_at=db_report.updated_at,
                created_by=db_report.created_by,
                metadata=db_report.report_metadata
            )

            service_logger.info("Report updated successfully in database", report_id=report_id)
            return report
        except Exception as e:
            db_session.rollback()
            service_logger.error("Failed to update report in database", error=str(e))
            return None
        finally:
            db_session.close()

    def delete_report(self, report_id: str) -> bool:
        """Delete a report and all associated data."""
        db_session = get_db_session()
        try:
            db_report = db_session.query(DBReport).filter(DBReport.id == report_id).first()
            if not db_report:
                service_logger.warning("Report not found in database for deletion", report_id=report_id)
                return False

            service_logger.info("Deleting report from database", report_id=report_id)

            # Delete the report (cascade will handle related data)
            db_session.delete(db_report)
            db_session.commit()

            service_logger.info("Report deleted successfully from database", report_id=report_id)
            return True
        except Exception as e:
            db_session.rollback()
            service_logger.error("Failed to delete report from database", error=str(e))
            return False
        finally:
            db_session.close()

    async def generate_report_data(self, report_id: str,
                                  force_refresh: bool = False) -> Dict[str, Any]:
        """Generate prediction data for a report."""
        db_session = get_db_session()
        try:
            # Get report from database
            db_report = db_session.query(DBReport).filter(DBReport.id == report_id).first()
            if not db_report:
                raise ValueError(f"Report {report_id} not found")

            if db_report.status == "processing":
                raise ValueError(f"Report {report_id} is already being processed")

            service_logger.info("Starting report generation", report_id=report_id)

            # Update report status
            db_report.status = "processing"
            db_report.updated_at = datetime.now()
            db_session.commit()

            # Convert to Report object for processing
            report = Report(
                id=db_report.id,
                title=db_report.title,
                description=db_report.description,
                topics=db_report.topics,
                status=db_report.status,
                prediction_year=db_report.prediction_year,
                confidence_threshold=db_report.confidence_threshold,
                created_at=db_report.created_at,
                updated_at=db_report.updated_at,
                created_by=db_report.created_by,
                metadata=db_report.report_metadata
            )

            # Load historical data
            historical_data = self._load_historical_data()

            # Generate predictions for each topic
            predictions = []
            for topic in report.topics:
                if topic not in historical_data:
                    service_logger.warning(f"Topic '{topic}' not found in historical data")
                    continue

                # Get enhanced data from DataLoader for better predictions
                enhanced_data = self.data_loader.get_topic_frequencies({}, topic)
                if enhanced_data:
                    # Use enhanced data if available
                    topic_historical = {topic: enhanced_data}
                    service_logger.info(f"Using enhanced data for {topic}", data_points=len(enhanced_data))
                else:
                    # Fallback to basic historical data
                    topic_historical = {topic: historical_data[topic]}
                    service_logger.info(f"Using basic historical data for {topic}", data_points=len(historical_data[topic]))

                # Use VQE predictor to get prediction
                prediction_request = self.vqe_predictor.PredictionRequest(
                    topics=[topic],
                    historical_years=5,
                    confidence_level=report.confidence_threshold,
                    force_classical=False
                )

                response = self.vqe_predictor.predict_topics(prediction_request, topic_historical)

                if response.predictions:
                    pred = response.predictions[0]
                    report_data = ReportData.create(
                        report_id=report_id,
                        topic=topic,
                        prediction_score=pred.importance,
                        confidence=(pred.confidence_interval[1] - pred.confidence_interval[0]) / 2,
                        trend=pred.trend,
                        historical_data=self._format_historical_data(topic_historical[topic]),
                        quantum_contribution=0.6 if not response.fallback_used else 0.0,
                        classical_contribution=0.4 if response.fallback_used else 1.0
                    )
                    predictions.append(report_data)

            # Store the data in database
            for prediction in predictions:
                db_report_data = DBReportData(
                    id=prediction.id,
                    report_id=prediction.report_id,
                    topic=prediction.topic,
                    prediction_score=prediction.prediction_score,
                    confidence=prediction.confidence,
                    trend=prediction.trend,
                    historical_data=prediction.historical_data,
                    quantum_contribution=prediction.quantum_contribution,
                    classical_contribution=prediction.classical_contribution,
                    created_at=prediction.created_at
                )
                db_session.add(db_report_data)

            # Generate visualizations using the dedicated service
            await self._generate_visualizations(report_id)

            # Update report status
            db_report.status = "completed"
            db_report.updated_at = datetime.now()
            db_session.commit()

            service_logger.info("Report generation completed", report_id=report_id,
                              predictions_count=len(predictions))

            return {
                "status": "completed",
                "predictions_count": len(predictions),
                "execution_time_ms": 0  # Would be calculated in real implementation
            }

        except Exception as e:
            db_session.rollback()
            service_logger.error("Report generation failed", report_id=report_id, error=str(e))
            # Update report status to failed
            try:
                db_report = db_session.query(DBReport).filter(DBReport.id == report_id).first()
                if db_report:
                    db_report.status = "failed"
                    db_report.updated_at = datetime.now()
                    db_session.commit()
            except Exception as update_error:
                service_logger.error("Failed to update report status to failed", error=str(update_error))
            raise
        finally:
            db_session.close()

    def get_report_data(self, report_id: str) -> List[ReportData]:
        """Get all data for a specific report."""
        db_session = get_db_session()
        try:
            db_report_data_list = db_session.query(DBReportData).filter(DBReportData.report_id == report_id).all()

            report_data_list = []
            for db_data in db_report_data_list:
                report_data = ReportData(
                    id=db_data.id,
                    report_id=db_data.report_id,
                    topic=db_data.topic,
                    prediction_score=db_data.prediction_score,
                    confidence=db_data.confidence,
                    trend=db_data.trend,
                    historical_data=db_data.historical_data,
                    quantum_contribution=db_data.quantum_contribution,
                    classical_contribution=db_data.classical_contribution,
                    created_at=db_data.created_at
                )
                report_data_list.append(report_data)

            service_logger.debug("Report data retrieved from database", report_id=report_id, count=len(report_data_list))
            return report_data_list
        except Exception as e:
            service_logger.error("Failed to retrieve report data from database", error=str(e))
            return []
        finally:
            db_session.close()

    def get_report_visualizations(self, report_id: str) -> List[Visualization]:
        """Get all visualizations for a specific report."""
        db_session = get_db_session()
        try:
            db_visualizations = db_session.query(DBVisualization).filter(DBVisualization.report_id == report_id).all()

            visualizations = []
            for db_viz in db_visualizations:
                visualization = Visualization(
                    id=db_viz.id,
                    report_id=db_viz.report_id,
                    type=db_viz.type,
                    title=db_viz.title,
                    data=db_viz.data,
                    config=db_viz.config,
                    created_at=db_viz.created_at,
                    updated_at=db_viz.updated_at
                )
                visualizations.append(visualization)

            service_logger.debug("Visualizations retrieved from database", report_id=report_id, count=len(visualizations))
            return visualizations
        except Exception as e:
            service_logger.error("Failed to retrieve visualizations from database", error=str(e))
            return []
        finally:
            db_session.close()

    def create_export_job(self, report_id: str, format: str) -> ExportJob:
        """Create a new export job for a report."""
        db_session = get_db_session()
        try:
            # Check if report exists
            db_report = db_session.query(DBReport).filter(DBReport.id == report_id).first()
            if not db_report:
                raise ValueError(f"Report {report_id} not found")

            service_logger.info("Creating export job in database", report_id=report_id, format=format)

            export_job = ExportJob.create(report_id=report_id, format=format)

            # Save to database
            db_export_job = DBExportJob(
                id=export_job.id,
                report_id=export_job.report_id,
                format=export_job.format,
                status=export_job.status,
                file_path=export_job.file_path,
                download_url=export_job.download_url,
                file_size_bytes=export_job.file_size_bytes,
                created_at=export_job.created_at,
                completed_at=export_job.completed_at,
                error_message=export_job.error_message
            )
            db_session.add(db_export_job)
            db_session.commit()

            service_logger.info("Export job created in database", export_job_id=export_job.id)
            return export_job
        except Exception as e:
            db_session.rollback()
            service_logger.error("Failed to create export job in database", error=str(e))
            raise
        finally:
            db_session.close()

    def get_export_jobs(self, report_id: str) -> List[ExportJob]:
        """Get all export jobs for a specific report."""
        db_session = get_db_session()
        try:
            db_export_jobs = db_session.query(DBExportJob).filter(DBExportJob.report_id == report_id).all()

            export_jobs = []
            for db_job in db_export_jobs:
                export_job = ExportJob(
                    id=db_job.id,
                    report_id=db_job.report_id,
                    format=db_job.format,
                    status=db_job.status,
                    file_path=db_job.file_path,
                    download_url=db_job.download_url,
                    file_size_bytes=db_job.file_size_bytes,
                    created_at=db_job.created_at,
                    completed_at=db_job.completed_at,
                    error_message=db_job.error_message
                )
                export_jobs.append(export_job)

            service_logger.debug("Export jobs retrieved from database", report_id=report_id, count=len(export_jobs))
            return export_jobs
        except Exception as e:
            service_logger.error("Failed to retrieve export jobs from database", error=str(e))
            return []
        finally:
            db_session.close()

    async def execute_export(self, export_job: ExportJob) -> str:
        """
        Execute an export job.

        Args:
            export_job: The export job to execute

        Returns:
            Path to the generated export file
        """
        db_session = get_db_session()
        try:
            # Get report from database
            db_report = db_session.query(DBReport).filter(DBReport.id == export_job.report_id).first()
            if not db_report:
                raise ValueError(f"Report {export_job.report_id} not found")

            # Convert to Report object
            report = Report(
                id=db_report.id,
                title=db_report.title,
                description=db_report.description,
                topics=db_report.topics,
                status=db_report.status,
                prediction_year=db_report.prediction_year,
                confidence_threshold=db_report.confidence_threshold,
                created_at=db_report.created_at,
                updated_at=db_report.updated_at,
                created_by=db_report.created_by,
                metadata=db_report.report_metadata
            )

            # Get data and visualizations from database
            data = self.get_report_data(export_job.report_id)
            visualizations = self.get_report_visualizations(export_job.report_id)

            service_logger.info("Executing export",
                              export_id=export_job.id,
                              format=export_job.format)

            try:
                if export_job.format == "pdf":
                    filepath = self.export_service.export_pdf(report, data, visualizations)
                elif export_job.format == "csv":
                    filepath = self.export_service.export_csv(report, data)
                elif export_job.format == "json":
                    filepath = self.export_service.export_json(report, data, visualizations)
                else:
                    raise ValueError(f"Unsupported export format: {export_job.format}")

                # Update export job status in database
                db_export_job = db_session.query(DBExportJob).filter(DBExportJob.id == export_job.id).first()
                if db_export_job:
                    db_export_job.status = "completed"
                    db_export_job.file_path = filepath
                    db_export_job.file_size_bytes = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                    db_export_job.completed_at = datetime.now()
                    db_session.commit()

                service_logger.info("Export completed",
                                  export_id=export_job.id,
                                  filepath=filepath)

                return filepath

            except Exception as e:
                service_logger.error("Export failed",
                                   export_id=export_job.id,
                                   error=str(e))
                # Update export job status to failed
                db_export_job = db_session.query(DBExportJob).filter(DBExportJob.id == export_job.id).first()
                if db_export_job:
                    db_export_job.status = "failed"
                    db_export_job.error_message = str(e)
                    db_export_job.completed_at = datetime.now()
                    db_session.commit()
                raise
        finally:
            db_session.close()

    def _validate_historical_data(self, data: Dict[str, List[float]]) -> Dict[str, List[float]]:
        """Validate and clean historical data."""
        validated_data = {}

        for topic, frequencies in data.items():
            # Filter out invalid frequencies and normalize if needed
            valid_freqs = []
            for freq in frequencies:
                if isinstance(freq, (int, float)):
                    # Normalize if frequency is in percentage format (0-100)
                    if freq > 1.0:
                        freq = freq / 100.0
                    # Check if normalized frequency is valid
                    if 0 <= freq <= 1:
                        valid_freqs.append(freq)

            if len(valid_freqs) < 2:
                service_logger.warning(f"Topic '{topic}' has insufficient valid data points", valid_points=len(valid_freqs))
                continue

            # Ensure we have at least some historical trend
            if len(valid_freqs) >= 2:
                validated_data[topic] = valid_freqs
                service_logger.debug(f"Validated data for {topic}", points=len(valid_freqs))

        service_logger.info("Historical data validation completed", valid_topics=len(validated_data))
        return validated_data

    def _load_historical_data(self) -> Dict[str, List[float]]:
        """Load historical data for predictions."""
        # Try to load from actual data files first
        data_files = [
            "data/historical_exam_data.csv",
            "data/exam_topics.csv",
            "src/data/historical_data.csv"
        ]

        for file_path in data_files:
            if Path(file_path).exists():
                try:
                    if file_path.endswith('.csv'):
                        loaded_data = self.data_loader.load_csv_data(file_path)
                        # Convert to the expected format
                        result = {}
                        for topic, records in loaded_data.items():
                            frequencies = self.data_loader.get_topic_frequencies(loaded_data, topic)
                            if frequencies:
                                result[topic] = frequencies
                        if result:
                            validated_result = self._validate_historical_data(result)
                            if validated_result:
                                service_logger.info("Loaded historical data from CSV", file_path=file_path)
                                return validated_result
                    elif file_path.endswith('.json'):
                        loaded_data = self.data_loader.load_json_data(file_path)
                        # Convert to the expected format
                        result = {}
                        for topic, records in loaded_data.items():
                            frequencies = self.data_loader.get_topic_frequencies(loaded_data, topic)
                            if frequencies:
                                result[topic] = frequencies
                        if result:
                            validated_result = self._validate_historical_data(result)
                            if validated_result:
                                service_logger.info("Loaded historical data from JSON", file_path=file_path)
                                return validated_result
                except Exception as e:
                    service_logger.warning(f"Failed to load data from {file_path}", error=str(e))
                    continue

        # Fallback to mock data if no real data files found
        service_logger.info("Using mock historical data (no real data files found)")
        mock_data = {
            "quantum_mechanics": [0.15, 0.18, 0.22, 0.25, 0.28],
            "linear_algebra": [0.20, 0.19, 0.21, 0.23, 0.24],
            "thermodynamics": [0.12, 0.14, 0.16, 0.18, 0.20],
            "calculus": [0.25, 0.26, 0.24, 0.27, 0.29],
            "probability": [0.18, 0.20, 0.19, 0.22, 0.24],
            "machine_learning": [0.08, 0.12, 0.15, 0.18, 0.22],
            "algorithms": [0.22, 0.24, 0.23, 0.26, 0.28],
            "data_structures": [0.30, 0.28, 0.32, 0.29, 0.31],
            "computer_networks": [0.16, 0.18, 0.17, 0.20, 0.19],
            "operating_systems": [0.14, 0.16, 0.15, 0.18, 0.17]
        }
        return self._validate_historical_data(mock_data)

    def _format_historical_data(self, data: List[float]) -> List[Dict[str, Any]]:
        """Format historical data for storage."""
        current_year = datetime.now().year
        return [
            {
                "year": current_year - len(data) + i + 1,
                "frequency": value,
                "percentage": round(value * 100, 2)
            }
            for i, value in enumerate(data)
        ]

    async def _generate_visualizations(self, report_id: str) -> None:
        """Generate visualizations for a report."""
        db_session = get_db_session()
        try:
            # Get report from database
            db_report = db_session.query(DBReport).filter(DBReport.id == report_id).first()
            if not db_report:
                return

            # Convert to Report object
            report = Report(
                id=db_report.id,
                title=db_report.title,
                description=db_report.description,
                topics=db_report.topics,
                status=db_report.status,
                prediction_year=db_report.prediction_year,
                confidence_threshold=db_report.confidence_threshold,
                created_at=db_report.created_at,
                updated_at=db_report.updated_at,
                created_by=db_report.created_by,
                metadata=db_report.report_metadata
            )

            # Get data from database
            data = self.get_report_data(report_id)
            if not data:
                return

            service_logger.info("Generating visualizations", report_id=report_id)

            # Use the dedicated visualization service
            visualizations = self.visualization_service.generate_visualizations(report, data)

            # Store the visualizations in database
            for viz in visualizations:
                db_visualization = DBVisualization(
                    id=viz.id,
                    report_id=viz.report_id,
                    type=viz.type,
                    title=viz.title,
                    data=viz.data,
                    config=viz.config,
                    created_at=viz.created_at,
                    updated_at=viz.updated_at
                )
                db_session.add(db_visualization)

            db_session.commit()

            service_logger.info("Visualizations generated and saved to database", report_id=report_id,
                              count=len(visualizations))
        except Exception as e:
            db_session.rollback()
            service_logger.error("Failed to generate visualizations", error=str(e))
        finally:
            db_session.close()
