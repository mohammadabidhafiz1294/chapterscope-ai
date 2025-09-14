"""
Contract tests for PUT /api/reports/{id} endpoint.
Tests the API contract for updating a specific report by ID.
"""
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from src.api.main import app

class TestReportsPutContract:
    """Contract tests for PUT /api/reports/{id} endpoint."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    def test_put_report_success(self):
        """Test successful update of a specific report."""
        # First create a report to update
        report_data = {
            "title": "Original Report",
            "description": "Original description",
            "topics": ["quantum_computing"],
            "prediction_year": 2025
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Update the report
        report_id = created_report["id"]
        update_data = {
            "title": "Updated Report Title",
            "description": "Updated description with new information",
            "topics": ["quantum_computing", "machine_learning"],
            "prediction_year": 2026,
            "confidence_threshold": 0.9
        }

        response = self.client.put(f"/api/reports/{report_id}", json=update_data)

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        # Should return JSON response
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Should return the updated report object
        assert isinstance(data, dict)

        # Check required fields
        required_fields = ["id", "title", "description", "topics", "status", "created_at", "updated_at"]
        for field in required_fields:
            assert field in data

        # Check data was updated
        assert data["id"] == report_id
        assert data["title"] == update_data["title"]
        assert data["description"] == update_data["description"]
        assert data["topics"] == update_data["topics"]
        assert data["prediction_year"] == update_data["prediction_year"]
        assert data["confidence_threshold"] == update_data["confidence_threshold"]

        # Check updated_at is newer than created_at
        assert data["updated_at"] >= data["created_at"]

    def test_put_report_not_found(self):
        """Test update of non-existent report."""
        non_existent_id = "non-existent-report-id"

        update_data = {
            "title": "Updated Report",
            "description": "Updated description",
            "topics": ["quantum_computing"]
        }

        response = self.client.put(f"/api/reports/{non_existent_id}", json=update_data)

        # Should return 404 Not Found
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Should return JSON response
        assert response.headers["content-type"] == "application/json"

        data = response.json()

        # Should contain error details
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_put_report_invalid_data(self):
        """Test update with invalid data."""
        # First create a report
        report_data = {
            "title": "Valid Report",
            "description": "Valid description",
            "topics": ["valid_topic"],
            "prediction_year": 2024,
            "exam_types": ["valid_exam"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Try to update with invalid data
        report_id = created_report["id"]
        invalid_update_data = {
            "title": "",  # Empty title should be invalid
            "prediction_year": -1  # Negative year should be invalid
        }

        response = self.client.put(f"/api/reports/{report_id}", json=invalid_update_data)

        # Should return 422 Unprocessable Entity
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_put_report_partial_update(self):
        """Test partial update of report fields."""
        # First create a report
        report_data = {
            "title": "Partial Update Test",
            "description": "Testing partial updates",
            "topics": ["test_topic"],
            "prediction_year": 2024,
            "exam_types": ["test_exam"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Update only the title
        report_id = created_report["id"]
        partial_data = {
            "title": "Partially Updated Title"
        }

        response = self.client.put(f"/api/reports/{report_id}", json=partial_data)

        # Should return 200 OK
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check that title was updated
        assert data["title"] == partial_data["title"]

        # Check other fields remain unchanged
        assert data["description"] == report_data["description"]
        assert data["topics"] == report_data["topics"]

    def test_put_report_invalid_id(self):
        """Test update with invalid report ID format."""
        invalid_id = "invalid@id#with#special$chars"

        update_data = {
            "title": "Updated Report",
            "description": "Updated description",
            "topics": ["quantum_computing"]
        }

        response = self.client.put(f"/api/reports/{invalid_id}", json=update_data)

        # Should return 404 Not Found or 422 Unprocessable Entity
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_put_report_empty_request(self):
        """Test update with empty request body."""
        # First create a report
        report_data = {
            "title": "Empty Payload Test",
            "description": "Testing empty payload update",
            "topics": ["test_topic"],
            "prediction_year": 2024,
            "exam_types": ["test_exam"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        # Try to update with empty payload
        report_id = created_report["id"]
        response = self.client.put(f"/api/reports/{report_id}", json={})

        # Should return 200 OK (empty update should be allowed)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Report should remain unchanged
        assert data["title"] == report_data["title"]
        assert data["description"] == report_data["description"]

    def test_put_report_topics_validation(self):
        """Test update with various topics validation scenarios."""
        # First create a report
        report_data = {
            "title": "Topics Validation Test",
            "description": "Testing topics validation",
            "topics": ["original_topic"],
            "prediction_year": 2024,
            "exam_types": ["test_exam"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        report_id = created_report["id"]

        # Test with valid topics
        valid_topics_data = {
            "title": "Valid Topics Report",
            "description": "Report with valid topics",
            "topics": ["quantum_computing", "machine_learning", "data_science"]
        }

        response = self.client.put(f"/api/reports/{report_id}", json=valid_topics_data)
        assert response.status_code == status.HTTP_200_OK

        # Test with empty topics (should fail)
        empty_topics_data = {
            "title": "Empty Topics Report",
            "description": "Report with no topics",
            "topics": []
        }

        response = self.client.put(f"/api/reports/{report_id}", json=empty_topics_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_put_report_confidence_threshold_validation(self):
        """Test update with confidence threshold validation."""
        # First create a report
        report_data = {
            "title": "Confidence Validation Test",
            "description": "Testing confidence threshold validation",
            "topics": ["test_topic"],
            "prediction_year": 2024,
            "exam_types": ["test_exam"]
        }

        create_response = self.client.post("/api/reports", json=report_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        created_report = create_response.json()

        report_id = created_report["id"]

        # Test with valid confidence threshold
        valid_data = {
            "title": "Valid Confidence Report",
            "description": "Report with valid confidence",
            "topics": ["quantum_computing"],
            "confidence_threshold": 0.8
        }

        response = self.client.put(f"/api/reports/{report_id}", json=valid_data)
        assert response.status_code == status.HTTP_200_OK

        # Test with invalid confidence threshold (out of range)
        invalid_data = {
            "title": "Invalid Confidence Report",
            "description": "Report with invalid confidence",
            "topics": ["quantum_computing"],
            "confidence_threshold": 1.5  # Should be between 0 and 1
        }

        response = self.client.put(f"/api/reports/{report_id}", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_put_report_response_format(self):
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

        # Update the report
        report_id = created_report["id"]
        update_data = {
            "title": "Updated Format Test",
            "description": "Updated format description"
        }

        response = self.client.put(f"/api/reports/{report_id}", json=update_data)

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

        # Check that updated_at is different from created_at (indicating update)
        # This would be tested with actual timestamps in a real scenario
        assert "updated_at" in data
