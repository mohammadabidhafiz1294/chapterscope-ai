"""
Contract tests for GET /api/reports endpoint.
Tests the API contract for retrieving all reports.
"""
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from src.api.main import app

class TestReportsGetContract:
    """Contract tests for GET /api/reports endpoint."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    def test_get_reports_success(self):
        """Test successful retrieval of all reports."""
        # This test should fail initially as the endpoint doesn't exist
        response = self.client.get("/api/reports")

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        # Should return JSON response
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Should return paginated response structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

        # Items should be a list
        assert isinstance(data["items"], list)

        # If there are reports, check structure
        if data["items"]:
            report = data["items"][0]
            required_fields = ["id", "title", "description", "topics", "status", "created_at"]
            for field in required_fields:
                assert field in report

    def test_get_reports_with_pagination(self):
        """Test reports retrieval with pagination parameters."""
        params = {
            "page": 1,
            "per_page": 10
        }

        response = self.client.get("/api/reports", params=params)

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Should return paginated response structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

        # Check pagination values
        assert data["page"] == 1
        assert data["per_page"] == 10
        assert isinstance(data["items"], list)

    def test_get_reports_with_filtering(self):
        """Test reports retrieval with filtering parameters."""
        params = {
            "status": "completed",
            "prediction_year": 2025
        }

        response = self.client.get("/api/reports", params=params)

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Should return paginated response structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

        # Should return filtered results
        assert isinstance(data["items"], list)

        # All returned reports should match the filter
        for report in data["items"]:
            if "status" in report:
                assert report["status"] == "completed"
            if "prediction_year" in report:
                assert report["prediction_year"] == 2025

    def test_get_reports_with_sorting(self):
        """Test reports retrieval with sorting parameters."""
        params = {
            "sort_by": "created_at",
            "sort_order": "desc"
        }

        response = self.client.get("/api/reports", params=params)

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Should return paginated response structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

        # Should return sorted results
        assert isinstance(data["items"], list)

        # Check that results are sorted by created_at desc
        if len(data["items"]) > 1:
            for i in range(len(data["items"]) - 1):
                assert data["items"][i]["created_at"] >= data["items"][i + 1]["created_at"]

    def test_get_reports_empty_result(self):
        """Test reports retrieval when no reports exist."""
        # This would require clearing the database first in a real scenario
        response = self.client.get("/api/reports")

        # Should return 200 OK even with empty results
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Should return paginated response structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

        # Should return empty list
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 0
        assert data["total"] == 0

    def test_get_reports_invalid_parameters(self):
        """Test reports retrieval with invalid parameters."""
        params = {
            "page": "invalid",
            "per_page": -1
        }

        response = self.client.get("/api/reports", params=params)

        # Should return 422 Unprocessable Entity for invalid parameters
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_reports_response_format(self):
        """Test response format matches expected schema."""
        response = self.client.get("/api/reports")

        # Should return proper JSON response
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Should return paginated response structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

        # Should be a list of report objects
        assert isinstance(data["items"], list)

        if data["items"]:
            report = data["items"][0]
            # Check data types
            assert isinstance(report["id"], str)
            assert isinstance(report["title"], str)
            assert isinstance(report["description"], str)
            assert isinstance(report["topics"], list)
            assert isinstance(report["status"], str)
            assert "created_at" in report
            assert "updated_at" in report
