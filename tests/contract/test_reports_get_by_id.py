"""
Contract tests for GET /api/reports/{id} endpoint.
Tests the API contract for retrieving a specific report by ID.
"""
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from src.api.main import app

class TestReportsGetByIdContract:
    """Contract tests for GET /api/reports/{id} endpoint."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    def test_get_report_by_id_success(self):
        """Test successful retrieval of a specific report."""
        # First create a report to retrieve
        report_data = {
            "title": "Test Report",
            "description": "A test report for contract testing",
            "topics": ["quantum_computing", "machine_learning"],
            "prediction_year": 2025,
            "exam_types": ["final_exam", "midterm"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Now retrieve the specific report
        report_id = created_report["id"]
        response = self.client.get(f"/api/reports/{report_id}")

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        # Should return JSON response
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Should return the report object
        assert isinstance(data, dict)

        # Check required fields
        required_fields = ["id", "title", "description", "topics", "status", "created_at", "updated_at"]
        for field in required_fields:
            assert field in data

        # Check data matches what was created
        assert data["id"] == report_id
        assert data["title"] == report_data["title"]
        assert data["description"] == report_data["description"]
        assert data["topics"] == report_data["topics"]

    def test_get_report_by_id_not_found(self):
        """Test retrieval of non-existent report."""
        non_existent_id = "non-existent-report-id"

        response = self.client.get(f"/api/reports/{non_existent_id}")

        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Should return JSON response
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Should contain error details
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_get_report_by_id_invalid_id(self):
        """Test retrieval with invalid report ID format."""
        invalid_id = "invalid@id#with#special$chars"

        response = self.client.get(f"/api/reports/{invalid_id}")

        # Should return 422 Unprocessable Entity or 404 Not Found
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_get_report_by_id_with_data(self):
        """Test retrieval of report with associated data."""
        # First create a report
        report_data = {
            "title": "Report with Data",
            "description": "Testing report with data fields",
            "topics": ["quantum_computing"],
            "prediction_year": 2025,
            "exam_types": ["final_exam"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Retrieve the report
        report_id = created_report["id"]
        response = self.client.get(f"/api/reports/{report_id}")

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check for optional data-related fields (may be empty initially)
        if "report_data" in data:
            assert isinstance(data["report_data"], (dict, type(None)))
        if "visualizations" in data:
            assert isinstance(data["visualizations"], list)
        if "export_jobs" in data:
            assert isinstance(data["export_jobs"], list)

    def test_get_report_by_id_with_visualizations(self):
        """Test retrieval of report with visualization data."""
        # First create a report
        report_data = {
            "title": "Report with Visualizations",
            "description": "Testing report with visualization fields",
            "topics": ["machine_learning"],
            "prediction_year": 2024,
            "exam_types": ["midterm"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Retrieve the report
        report_id = created_report["id"]
        response = self.client.get(f"/api/reports/{report_id}")

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check visualizations structure (may be empty initially)
        if "visualizations" in data:
            assert isinstance(data["visualizations"], list)

            if data["visualizations"]:
                viz = data["visualizations"][0]
                required_viz_fields = ["id", "type", "title", "data", "config"]
                for field in required_viz_fields:
                    assert field in viz

    def test_get_report_by_id_with_export_history(self):
        """Test retrieval of report with export history."""
        # First create a report
        report_data = {
            "title": "Report with Export History",
            "description": "Testing report with export history",
            "topics": ["data_science"],
            "prediction_year": 2026,
            "exam_types": ["final_exam"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Retrieve the report
        report_id = created_report["id"]
        response = self.client.get(f"/api/reports/{report_id}")

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check export history structure (may be empty initially)
        if "export_jobs" in data:
            assert isinstance(data["export_jobs"], list)

            if data["export_jobs"]:
                export = data["export_jobs"][0]
                required_export_fields = ["id", "format", "created_at", "status", "download_url"]
                for field in required_export_fields:
                    assert field in export

    def test_get_report_by_id_response_format(self):
        """Test response format matches expected schema."""
        # First create a report
        report_data = {
            "title": "Format Test Report",
            "description": "Testing response format",
            "topics": ["test_topic"],
            "prediction_year": 2024,
            "exam_types": ["test_exam"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Retrieve the report
        report_id = created_report["id"]
        response = self.client.get(f"/api/reports/{report_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check data types
        assert isinstance(data["id"], str)
        assert isinstance(data["title"], str)
        assert isinstance(data["description"], str)
        assert isinstance(data["topics"], list)
        assert isinstance(data["status"], str)
        assert "created_at" in data
        assert "updated_at" in data

        # Check topics structure
        for topic in data["topics"]:
            assert isinstance(topic, str)

        # Check status is valid
        valid_statuses = ["pending", "processing", "completed", "failed"]
        assert data["status"] in valid_statuses

    def test_get_report_by_id_empty_id(self):
        """Test retrieval with empty report ID."""
        response = self.client.get("/api/reports/")

        # This should actually hit the GET /api/reports endpoint (list all)
        # and return 200 OK with paginated results
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Should return paginated response structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

    def test_get_report_by_id_special_characters(self):
        """Test retrieval with special characters in ID."""
        # Test with URL-encoded special characters
        special_id = "report%20with%20spaces%2Bplus"

        response = self.client.get(f"/api/reports/{special_id}")

        # Should handle URL-encoded IDs properly
        # Either return 200 OK with decoded ID or 404 Not Found
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
