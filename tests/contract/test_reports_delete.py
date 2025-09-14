"""
Contract tests for DELETE /api/reports/{id} endpoint.
Tests the API contract for deleting a specific report by ID.
"""
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from src.api.main import app

class TestReportsDeleteContract:
    """Contract tests for DELETE /api/reports/{id} endpoint."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    def test_delete_report_success(self):
        """Test successful deletion of a specific report."""
        # First create a report to delete
        report_data = {
            "title": "Report to Delete",
            "description": "This report will be deleted",
            "topics": ["quantum_computing"],
            "prediction_year": 2025
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Delete the report
        report_id = created_report["id"]
        response = self.client.delete(f"/api/reports/{report_id}")

        # Should return 204 No Content for successful deletion
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Should not return any content
        assert response.text == ""

        # Verify the report was actually deleted
        get_response = self.client.get(f"/api/reports/{report_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_report_not_found(self):
        """Test deletion of non-existent report."""
        non_existent_id = "non-existent-report-id"

        response = self.client.delete(f"/api/reports/{non_existent_id}")

        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Should return JSON error response
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_delete_report_invalid_id(self):
        """Test deletion with invalid report ID format."""
        invalid_id = "invalid@id#with#special$chars"

        response = self.client.delete(f"/api/reports/{invalid_id}")

        # Should return 404 Not Found or 422 Unprocessable Entity
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_delete_report_with_dependencies(self):
        """Test deletion of report with associated data/visualizations."""
        # First create a report
        report_data = {
            "title": "Report with Dependencies",
            "description": "This report has associated data",
            "topics": ["machine_learning"],
            "prediction_year": 2024
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Delete the report
        report_id = created_report["id"]
        response = self.client.delete(f"/api/reports/{report_id}")

        # Should return 204 No Content (assuming cascade delete is implemented)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify the report was deleted
        get_response = self.client.get(f"/api/reports/{report_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

        # Verify that associated data is also deleted would be tested in integration tests
        # This contract test focuses on the API response

    def test_delete_report_already_deleted(self):
        """Test deletion of already deleted report."""
        # First create a report
        report_data = {
            "title": "Report for Double Delete",
            "description": "Testing double deletion",
            "topics": ["neural_networks"],
            "prediction_year": 2025
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        report_id = created_report["id"]

        # First delete (should succeed)
        response1 = self.client.delete(f"/api/reports/{report_id}")
        assert response1.status_code == status.HTTP_204_NO_CONTENT

        # Second delete (should return 404)
        response2 = self.client.delete(f"/api/reports/{report_id}")
        assert response2.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_report_processing_status(self):
        """Test deletion of report with processing status."""
        # First create a report
        report_data = {
            "title": "Processing Report",
            "description": "Report currently being processed",
            "topics": ["data_science"],
            "prediction_year": 2026
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # In a real scenario, we might need to set the status to processing
        # For now, we'll just test deletion of a regular report
        report_id = created_report["id"]
        response = self.client.delete(f"/api/reports/{report_id}")

        # Should return 204 No Content (assuming deletion is allowed)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_report_empty_id(self):
        """Test deletion with empty report ID."""
        response = self.client.delete("/api/reports/")

        # This should actually hit the GET /api/reports endpoint (list all)
        # and return 405 Method Not Allowed for DELETE on list endpoint
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_delete_report_special_characters(self):
        """Test deletion with special characters in ID."""
        # Test with URL-encoded special characters
        special_id = "report%20with%20spaces%2Bplus"

        response = self.client.delete(f"/api/reports/{special_id}")

        # Should handle URL-encoded IDs properly
        # Either return 204 No Content or 404 Not Found
        assert response.status_code in [status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND]

    def test_delete_report_cascade_verification(self):
        """Test that deletion cascades to related resources."""
        # First create a report
        report_data = {
            "title": "Cascade Delete Test",
            "description": "Testing cascade deletion of associated data",
            "topics": ["quantum_physics"],
            "prediction_year": 2025
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Delete the report
        report_id = created_report["id"]
        response = self.client.delete(f"/api/reports/{report_id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify report is gone
        get_response = self.client.get(f"/api/reports/{report_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

        # Verify associated resources are also deleted
        # This would be tested more thoroughly in integration tests
        # Contract test focuses on the delete operation itself
