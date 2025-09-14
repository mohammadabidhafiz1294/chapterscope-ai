"""FastAPI routes for report management endpoints."""

import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.models import (
    ReportCreateRequest, ReportUpdateRequest, ReportResponse,
    ReportListResponse, ReportGenerationRequest, ReportGenerationResponse,
    ReportExportRequest, ReportExportResponse, ReportDataResponse,
    ReportDataListResponse
)
from src.config import service_logger
from src.services.report_service import ReportService

# Initialize router
router = APIRouter()

# Initialize service (in production, this would be injected)
report_service = ReportService()


@router.post("/reports", response_model=ReportResponse, status_code=201)
async def create_report(request: ReportCreateRequest) -> ReportResponse:
    """
    Create a new prediction report.

    Generates a report configuration for analyzing specified topics.
    The report will be in 'pending' status until generation is triggered.
    """
    try:
        report = report_service.create_report(request)

        return ReportResponse(
            id=report.id,
            title=report.title,
            description=report.description,
            topics=report.topics,
            status=report.status,
            prediction_year=report.prediction_year,
            confidence_threshold=report.confidence_threshold,
            created_at=report.created_at,
            updated_at=report.updated_at,
            created_by=report.created_by
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create report: {str(e)}")


@router.get("/reports", response_model=ReportListResponse)
async def get_reports(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status")
) -> ReportListResponse:
    """
    Retrieve all reports with pagination and filtering.

    Returns a paginated list of reports with optional status filtering.
    """
    try:
        result = report_service.get_all_reports(
            page=page,
            per_page=per_page,
            status_filter=status
        )

        # Convert reports to response models
        items = []
        for report in result["items"]:
            items.append(ReportResponse(
                id=report.id,
                title=report.title,
                description=report.description,
                topics=report.topics,
                status=report.status,
                prediction_year=report.prediction_year,
                confidence_threshold=report.confidence_threshold,
                created_at=report.created_at,
                updated_at=report.updated_at,
                created_by=report.created_by
            ))

        return ReportListResponse(
            items=items,
            total=result["total"],
            page=result["page"],
            per_page=result["per_page"],
            pages=result["pages"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve reports: {str(e)}")


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(report_id: str) -> ReportResponse:
    """
    Retrieve a specific report by ID.

    Returns detailed information about a report including its data and visualizations.
    """
    try:
        report = report_service.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        # Get associated data
        data = report_service.get_report_data(report_id)
        visualizations = report_service.get_report_visualizations(report_id)
        export_history = report_service.get_export_jobs(report_id)

        return ReportResponse(
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
            data=[{
                "topic": item.topic,
                "prediction_score": item.prediction_score,
                "confidence": item.confidence,
                "trend": item.trend,
                "historical_data": item.historical_data,
                "quantum_contribution": item.quantum_contribution,
                "classical_contribution": item.classical_contribution
            } for item in data],
            visualizations=[{
                "id": viz.id,
                "type": viz.type,
                "title": viz.title,
                "data": viz.data,
                "config": viz.config
            } for viz in visualizations],
            export_history=[{
                "id": job.id,
                "format": job.format,
                "created_at": job.created_at,
                "status": job.status,
                "download_url": job.download_url,
                "file_size_bytes": job.file_size_bytes
            } for job in export_history]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve report: {str(e)}")


@router.put("/reports/{report_id}", response_model=ReportResponse)
async def update_report(report_id: str, request: ReportUpdateRequest) -> ReportResponse:
    """
    Update an existing report.

    Allows updating report metadata and configuration.
    Note: Cannot update reports that are currently being processed.
    """
    try:
        report = report_service.update_report(report_id, request)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        return ReportResponse(
            id=report.id,
            title=report.title,
            description=report.description,
            topics=report.topics,
            status=report.status,
            prediction_year=report.prediction_year,
            confidence_threshold=report.confidence_threshold,
            created_at=report.created_at,
            updated_at=report.updated_at,
            created_by=report.created_by
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update report: {str(e)}")


@router.delete("/reports/{report_id}", status_code=204)
async def delete_report(report_id: str) -> None:
    """
    Delete a report and all associated data.

    Permanently removes the report and all its generated data, visualizations, and export history.
    """
    try:
        success = report_service.delete_report(report_id)
        if not success:
            raise HTTPException(status_code=404, detail="Report not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {str(e)}")


@router.post("/reports/{report_id}/generate", response_model=ReportGenerationResponse, status_code=202)
async def generate_report(report_id: str, request: Optional[ReportGenerationRequest] = None) -> ReportGenerationResponse:
    """
    Trigger report generation.

    Starts the asynchronous process of generating predictions and visualizations for the report.
    Returns a job ID that can be used to track progress.
    """
    try:
        # Check if report exists
        report = report_service.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        # Check if report is already being processed
        if report.status == "processing":
            raise HTTPException(
                status_code=409,
                detail="Report is already being processed"
            )

        # Start generation (in a real implementation, this would be async)
        import asyncio
        generation_params = request.dict() if request else {}

        # For now, we'll simulate the async behavior
        # In production, this would queue the job
        job_id = f"job_{report_id}"

        # Start background task (simplified for now)
        asyncio.create_task(
            report_service.generate_report_data(
                report_id,
                force_refresh=generation_params.get("force_refresh", False)
            )
        )

        return ReportGenerationResponse(
            job_id=job_id,
            status="processing",
            message="Report generation started",
            estimated_completion_time=30  # seconds
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start report generation: {str(e)}")


@router.get("/reports/{report_id}/export", response_model=List[ReportExportResponse])
async def get_report_exports(report_id: str) -> List[ReportExportResponse]:
    """
    Get export history for a report.

    Returns a list of all export jobs for the specified report.
    """
    try:
        # Check if report exists
        report = report_service.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        export_jobs = report_service.get_export_jobs(report_id)

        return [
            ReportExportResponse(
                export_id=job.id,
                status=job.status,
                format=job.format,
                download_url=job.download_url,
                file_size_bytes=job.file_size_bytes,
                created_at=job.created_at,
                estimated_completion_time=10 if job.status == "processing" else None
            )
            for job in export_jobs
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve export history: {str(e)}")


@router.post("/reports/{report_id}/export", response_model=ReportExportResponse, status_code=202)
async def export_report(report_id: str, request: ReportExportRequest) -> ReportExportResponse:
    """
    Create a new export job for a report.

    Starts the process of exporting the report in the specified format.
    """
    try:
        # Check if report exists
        report = report_service.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        # Create export job
        export_job = report_service.create_export_job(report_id, request.format)

        # Execute export asynchronously
        async def execute_export_task():
            try:
                await report_service.execute_export(export_job)
            except Exception as e:
                service_logger.error("Export task failed", export_id=export_job.id, error=str(e))
                export_job.status = "failed"
                export_job.error_message = str(e)
                export_job.completed_at = datetime.now()

        asyncio.create_task(execute_export_task())

        return ReportExportResponse(
            export_id=export_job.id,
            status=export_job.status,
            format=export_job.format,
            download_url=None,  # Will be set when export completes
            file_size_bytes=None,
            created_at=export_job.created_at,
            estimated_completion_time=30  # seconds
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create export job: {str(e)}")


@router.get("/reports/{report_id}/data", response_model=ReportDataListResponse)
async def get_report_data(report_id: str) -> ReportDataListResponse:
    """
    Get prediction data for a specific report.

    Returns detailed prediction results including scores, confidence levels,
    trends, and historical data for each analyzed topic.
    """
    try:
        # Check if report exists
        report = report_service.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        # Get report data
        data_entries = report_service.get_report_data(report_id)

        # Convert to response format
        items = [
            ReportDataResponse(
                id=data.id,
                report_id=data.report_id,
                topic=data.topic,
                prediction_score=data.prediction_score,
                confidence=data.confidence,
                trend=data.trend,
                historical_data=data.historical_data,
                quantum_contribution=data.quantum_contribution,
                classical_contribution=data.classical_contribution,
                created_at=data.created_at
            )
            for data in data_entries
        ]

        return ReportDataListResponse(
            report_id=report_id,
            items=items,
            total_count=len(items)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve report data: {str(e)}")


@router.get("/reports/{report_id}/visualizations")
async def get_report_visualizations(report_id: str) -> JSONResponse:
    """
    Get visualizations for a report.

    Returns visualization data that can be used with Chart.js or similar libraries.
    """
    try:
        # Check if report exists
        report = report_service.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        visualizations = report_service.get_report_visualizations(report_id)

        return JSONResponse(content={
            "report_id": report_id,
            "visualizations": [
                {
                    "id": viz.id,
                    "type": viz.type,
                    "title": viz.title,
                    "data": viz.data,
                    "config": viz.config
                }
                for viz in visualizations
            ]
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve visualizations: {str(e)}")
