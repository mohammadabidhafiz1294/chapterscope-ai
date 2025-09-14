"""Contract tests for POST /api/reports/{id}/export endpoint."""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.main import app

# Create test client
client = TestClient(app)


class TestReportsExportContract:
    """Contract tests for report export endpoint."""

    def test_export_report_success_pdf(self):
        """Test successful report export in PDF format."""
        # First create a report
        report_data = {
            "title": "Test Report for PDF Export",
            "description": "Report for testing PDF export functionality",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Request PDF export
        export_request = {"format": "pdf"}
        response = client.post(f"/api/reports/{report_id}/export", json=export_request)

        # Should return 202 Accepted
        assert response.status_code == status.HTTP_202_ACCEPTED

        data = response.json()

        # Check response structure
        assert "export_id" in data
        assert "status" in data
        assert "format" in data
        assert data["format"] == "pdf"
        assert "download_url" in data
        assert "created_at" in data

    def test_export_report_success_csv(self):
        """Test successful report export in CSV format."""
        # First create a report
        report_data = {
            "title": "Test Report for CSV Export",
            "description": "Report for testing CSV export functionality",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Request CSV export
        export_request = {"format": "csv"}
        response = client.post(f"/api/reports/{report_id}/export", json=export_request)

        # Should return 202 Accepted
        assert response.status_code == status.HTTP_202_ACCEPTED

        data = response.json()
        assert data["format"] == "csv"

    def test_export_report_success_json(self):
        """Test successful report export in JSON format."""
        # First create a report
        report_data = {
            "title": "Test Report for JSON Export",
            "description": "Report for testing JSON export functionality",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Request JSON export
        export_request = {"format": "json"}
        response = client.post(f"/api/reports/{report_id}/export", json=export_request)

        # Should return 202 Accepted
        assert response.status_code == status.HTTP_202_ACCEPTED

        data = response.json()
        assert data["format"] == "json"

    def test_export_report_not_found(self):
        """Test export request for non-existent report."""
        non_existent_id = "non_existent_report_123"

        export_request = {"format": "pdf"}
        response = client.post(f"/api/reports/{non_existent_id}/export", json=export_request)

        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_export_report_invalid_format(self):
        """Test export request with invalid format."""
        # First create a report
        report_data = {
            "title": "Test Report Invalid Format",
            "description": "Report for testing invalid export format",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Request invalid format
        export_request = {"format": "invalid_format"}
        response = client.post(f"/api/reports/{report_id}/export", json=export_request)

        # Should return 422 Unprocessable Entity for invalid format
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_export_report_missing_format(self):
        """Test export request with missing format field."""
        # First create a report
        report_data = {
            "title": "Test Report Missing Format",
            "description": "Report for testing missing export format",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Request without format
        export_request = {}
        response = client.post(f"/api/reports/{report_id}/export", json=export_request)

        # Should return 422 Unprocessable Entity for missing required field
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_export_report_invalid_id(self):
        """Test export request with invalid report ID format."""
        invalid_id = "invalid@id#with#special$chars"

        export_request = {"format": "pdf"}
        response = client.post(f"/api/reports/{invalid_id}/export", json=export_request)

        # Should return 404 Not Found or 405 Method Not Allowed
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_export_report_empty_id(self):
        """Test export request with empty report ID."""
        export_request = {"format": "pdf"}
        response = client.post("/api/reports//export", json=export_request)

        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_export_report_response_format(self):
        """Test export response format matches expected schema."""
        # First create a report
        report_data = {
            "title": "Test Report Response Format",
            "description": "Report for testing export response format",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Request export
        export_request = {"format": "pdf"}
        response = client.post(f"/api/reports/{report_id}/export", json=export_request)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Should return proper JSON response
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Validate response structure
        assert isinstance(data, dict)
        assert isinstance(data["export_id"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["format"], str)
        assert isinstance(data["download_url"], (str, type(None)))
        assert isinstance(data["created_at"], str)

        # Check optional fields
        if "file_size_bytes" in data:
            assert isinstance(data["file_size_bytes"], (int, type(None)))

        if "estimated_completion_time" in data:
            assert isinstance(data["estimated_completion_time"], (int, type(None)))

    def test_export_report_with_visualizations(self):
        """Test export request with visualizations included."""
        # First create a report
        report_data = {
            "title": "Test Report with Visualizations",
            "description": "Report for testing export with visualizations",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Request PDF export with visualizations
        export_request = {
            "format": "pdf",
            "include_visualizations": True
        }
        response = client.post(f"/api/reports/{report_id}/export", json=export_request)

        # Should return 202 Accepted
        assert response.status_code == status.HTTP_202_ACCEPTED

        data = response.json()
        assert data["format"] == "pdf"

    def test_export_report_multiple_formats(self):
        """Test multiple export requests for different formats."""
        # First create a report
        report_data = {
            "title": "Test Report Multiple Formats",
            "description": "Report for testing multiple export formats",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Request multiple exports
        formats = ["pdf", "csv", "json"]
        export_ids = []

        for fmt in formats:
            export_request = {"format": fmt}
            response = client.post(f"/api/reports/{report_id}/export", json=export_request)
            assert response.status_code == status.HTTP_202_ACCEPTED

            data = response.json()
            assert data["format"] == fmt
            export_ids.append(data["export_id"])

        # Verify all export IDs are unique
        assert len(set(export_ids)) == len(export_ids)
