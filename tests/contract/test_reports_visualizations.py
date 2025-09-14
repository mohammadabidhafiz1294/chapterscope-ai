"""Contract tests for GET /api/reports/{id}/visualizations endpoint."""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.main import app

# Create test client
client = TestClient(app)


class TestReportsVisualizationsContract:
    """Contract tests for report visualizations endpoint."""

    def test_get_visualizations_success(self):
        """Test successful retrieval of report visualizations."""
        # First create a report
        report_data = {
            "title": "Test Report for Visualizations",
            "description": "Report for testing visualization retrieval",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Get visualizations
        response = client.get(f"/api/reports/{report_id}/visualizations")

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check response structure
        assert "report_id" in data
        assert data["report_id"] == report_id
        assert "visualizations" in data
        assert isinstance(data["visualizations"], list)

    def test_get_visualizations_not_found(self):
        """Test retrieval of visualizations for non-existent report."""
        non_existent_id = "non_existent_report_123"

        response = client.get(f"/api/reports/{non_existent_id}/visualizations")

        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_visualizations_invalid_id(self):
        """Test retrieval of visualizations with invalid report ID format."""
        invalid_id = "invalid@id#with#special$chars"

        response = client.get(f"/api/reports/{invalid_id}/visualizations")

        # Should return 404 Not Found or 422 Unprocessable Entity
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_get_visualizations_empty_id(self):
        """Test retrieval of visualizations with empty report ID."""
        response = client.get("/api/reports//visualizations")

        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_visualizations_structure(self):
        """Test that visualizations have correct structure."""
        # First create a report
        report_data = {
            "title": "Test Report Structure",
            "description": "Report for testing visualization structure",
            "topics": ["quantum_computing", "machine_learning"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Get visualizations
        response = client.get(f"/api/reports/{report_id}/visualizations")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check visualizations array
        for viz in data["visualizations"]:
            assert "id" in viz
            assert "type" in viz
            assert "title" in viz
            assert "data" in viz
            assert "config" in viz

            # Check data types
            assert isinstance(viz["id"], str)
            assert isinstance(viz["type"], str)
            assert isinstance(viz["title"], str)
            assert isinstance(viz["data"], dict)
            assert isinstance(viz["config"], dict)

    def test_get_visualizations_response_format(self):
        """Test response format matches expected JSON schema."""
        # First create a report
        report_data = {
            "title": "Test Report Format",
            "description": "Report for testing response format",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        response = client.get(f"/api/reports/{report_id}/visualizations")

        # Should return proper JSON response
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Validate top-level structure
        assert isinstance(data, dict)
        assert "report_id" in data
        assert "visualizations" in data

        # Validate visualizations is an array
        assert isinstance(data["visualizations"], list)

    def test_get_visualizations_after_generation(self):
        """Test visualizations are available after report generation."""
        # First create a report
        report_data = {
            "title": "Test Report After Generation",
            "description": "Report for testing visualizations after generation",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Trigger generation
        gen_response = client.post(f"/api/reports/{report_id}/generate")
        assert gen_response.status_code == status.HTTP_202_ACCEPTED

        # Get visualizations
        response = client.get(f"/api/reports/{report_id}/visualizations")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Should have visualizations after generation
        # (May be empty if generation is still in progress or no data available)
        assert isinstance(data["visualizations"], list)

    def test_get_visualizations_multiple_topics(self):
        """Test visualizations for reports with multiple topics."""
        # First create a report with multiple topics
        report_data = {
            "title": "Multi-Topic Report",
            "description": "Report with multiple topics for visualization testing",
            "topics": ["quantum_computing", "machine_learning", "algorithms"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Get visualizations
        response = client.get(f"/api/reports/{report_id}/visualizations")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Should return visualizations array
        assert "visualizations" in data
        assert isinstance(data["visualizations"], list)

    def test_get_visualizations_content_types(self):
        """Test that visualizations contain expected content types."""
        # First create a report
        report_data = {
            "title": "Content Types Test",
            "description": "Report for testing visualization content types",
            "topics": ["quantum_computing"],
            "prediction_year": 2024,
            "confidence_threshold": 0.8
        }
        create_response = client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        report_id = create_response.json()["id"]

        # Trigger generation to create visualizations
        gen_response = client.post(f"/api/reports/{report_id}/generate")
        assert gen_response.status_code == status.HTTP_202_ACCEPTED

        # Get visualizations
        response = client.get(f"/api/reports/{report_id}/visualizations")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # If visualizations exist, check their types
        for viz in data["visualizations"]:
            # Common visualization types
            assert viz["type"] in ["bar", "line", "pie", "scatter", "trend", "histogram"]

            # Check that data contains expected structure
            assert "labels" in viz["data"] or "datasets" in viz["data"]

    def test_get_visualizations_error_handling(self):
        """Test error handling for visualizations endpoint."""
        # Test with malformed report ID
        response = client.get("/api/reports/malformed-id-!@#$%/visualizations")

        # Should handle gracefully
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_422_UNPROCESSABLE_ENTITY]
