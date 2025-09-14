"""Contract test for POST /api/reports endpoint."""

import pytest
from fastapi.testclient import TestClient
from fastapi import status


class TestReportsPostContract:
    """Contract tests for POST /api/reports endpoint."""

    def setup_method(self):
        """Set up test client."""
        from src.api.main import app
        self.client = TestClient(app)

    def test_post_reports_success(self):
        """Test successful report creation."""
        # This test should fail initially as the endpoint doesn't exist
        report_data = {
            "title": "Q4 2025 Exam Topic Analysis",
            "description": "Analysis of predicted exam topics for Q4 2025",
            "topics": ["quantum-mechanics", "linear-algebra", "thermodynamics"],
            "prediction_year": 2025,
            "confidence_threshold": 0.8
        }

        response = self.client.post("/api/reports", json=report_data)

        # Should return 201 Created
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert "id" in data
        assert "title" in data
        assert "description" in data
        assert "created_at" in data
        assert "status" in data
        assert data["status"] == "pending"

    def test_post_reports_invalid_data(self):
        """Test report creation with invalid data."""
        # Empty request
        response = self.client.post("/api/reports", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_post_reports_missing_required_fields(self):
        """Test report creation with missing required fields."""
        # Missing title
        report_data = {
            "description": "Analysis of predicted exam topics",
            "topics": ["quantum-mechanics"]
        }

        response = self.client.post("/api/reports", json=report_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_post_reports_empty_topics(self):
        """Test report creation with empty topics list."""
        report_data = {
            "title": "Empty Topics Report",
            "description": "Report with no topics",
            "topics": []
        }

        response = self.client.post("/api/reports", json=report_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_post_reports_response_format(self):
        """Test response format matches expected schema."""
        report_data = {
            "title": "Format Test Report",
            "description": "Testing response format",
            "topics": ["quantum-mechanics"],
            "prediction_year": 2025
        }

        response = self.client.post("/api/reports", json=report_data)

        # Should return proper JSON response
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        # Check that all expected fields are present
        required_fields = ["id", "title", "description", "topics", "status", "created_at"]
        for field in required_fields:
            assert field in data
