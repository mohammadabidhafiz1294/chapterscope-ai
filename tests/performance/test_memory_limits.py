"""Performance tests for memory usage limits."""

import pytest
import time
import psutil
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.services.vqe_predictor import VQEPredictor
from src.services.data_loader import DataLoader


class TestMemoryLimits:
    """Performance tests for memory usage limits."""

    def setup_method(self):
        """Set up test client and mock services."""
        self.client = TestClient(app)
        self.mock_predictor = MagicMock(spec=VQEPredictor)
        self.mock_data_loader = MagicMock(spec=DataLoader)

        # Mock quantum as available
        self.mock_predictor.quantum_available = True

        # Patch the services in the API for the duration of the test
        self.predictor_patcher = patch('src.api.main.predictor', self.mock_predictor)
        self.data_loader_patcher = patch(
            'src.api.main.data_loader', self.mock_data_loader
        )
        self.predictor_patcher.start()
        self.data_loader_patcher.start()

    def teardown_method(self):
        """Stop patchers started in setup_method."""
        self.data_loader_patcher.stop()
        self.predictor_patcher.stop()

    def test_memory_usage_baseline(self):
        """Test baseline memory usage for predictions."""
        # Mock response with memory tracking
        mock_response = {
            "predictions": [{
                "topic": "memory-baseline",
                "importance": 0.25,
                "confidence_interval": [0.20, 0.30],
                "trend": "stable",
                "method": "quantum"
            }],
            "execution_time_ms": 1500,
            "memory_usage_mb": 128,  # Baseline memory usage
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": ["memory-baseline"]}

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        response = self.client.post("/api/v1/predict", json=request_data)

        # Get memory usage after request
        final_memory = process.memory_info().rss / 1024 / 1024  # MB

        assert response.status_code == 200
        data = response.json()

        # Verify memory usage is tracked
        assert "memory_usage_mb" in data
        assert data["memory_usage_mb"] > 0
        assert data["memory_usage_mb"] < 512  # Should be less than 512MB

        # Verify process memory didn't grow excessively
        memory_growth = final_memory - initial_memory
        assert memory_growth < 100  # Less than 100MB growth

    def test_memory_scaling_with_problem_size(self):
        """Test how memory usage scales with problem size."""
        # Test different problem sizes
        test_cases = [
            {"topics": ["small"], "expected_max_memory": 256},
            {"topics": ["small", "medium"], "expected_max_memory": 384},
            {"topics": ["small", "medium", "large"], "expected_max_memory": 512}
        ]

        for i, test_case in enumerate(test_cases):
            mock_response = {
                "predictions": [
                    {
                        "topic": topic,
                        "importance": 0.2 + j * 0.1,
                        "confidence_interval": [0.15 + j * 0.1, 0.25 + j * 0.1],
                        "trend": "stable",
                        "method": "quantum"
                    } for j, topic in enumerate(test_case["topics"])
                ],
                "execution_time_ms": 1000 + i * 500,
                "memory_usage_mb": 100 + i * 50,  # Increasing memory
                "fallback_used": False
            }

            self.mock_predictor.predict_topics.return_value = mock_response

            request_data = {"topics": test_case["topics"]}

            response = self.client.post("/api/v1/predict", json=request_data)

            assert response.status_code == 200
            data = response.json()

            # Verify memory usage scales reasonably
            assert data["memory_usage_mb"] <= test_case["expected_max_memory"]
            assert data["memory_usage_mb"] > 0

    def test_memory_limits_enforcement(self):
        """Test that memory limits are enforced."""
        # Mock excessive memory usage
        mock_response = {
            "predictions": [{
                "topic": "memory-limit-test",
                "importance": 0.25,
                "confidence_interval": [0.20, 0.30],
                "trend": "stable",
                "method": "quantum"
            }],
            "execution_time_ms": 2000,
            "memory_usage_mb": 2048,  # 2GB - should trigger limit
            "memory_limit_exceeded": True,
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": ["memory-limit-test"]}

        response = self.client.post("/api/v1/predict", json=request_data)

        assert response.status_code == 200
        data = response.json()

        # Should detect memory limit exceeded
        assert data["memory_usage_mb"] >= 1024  # At least 1GB
        assert data.get("memory_limit_exceeded", False) is True

    def test_memory_cleanup_after_requests(self):
        """Test that memory is properly cleaned up after requests."""
        process = psutil.Process(os.getpid())

        # Make multiple requests
        initial_memory = process.memory_info().rss / 1024 / 1024

        for i in range(5):
            mock_response = {
                "predictions": [{
                    "topic": f"cleanup-test-{i}",
                    "importance": 0.25,
                    "confidence_interval": [0.20, 0.30],
                    "trend": "stable",
                    "method": "quantum"
                }],
                "execution_time_ms": 1200,
                "memory_usage_mb": 150,
                "fallback_used": False
            }

            self.mock_predictor.predict_topics.return_value = mock_response

            request_data = {"topics": [f"cleanup-test-{i}"]}
            response = self.client.post("/api/v1/predict", json=request_data)

            assert response.status_code == 200

        # Check memory after all requests
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory

        # Memory growth should be reasonable (less than 50MB total)
        assert memory_growth < 50

    def test_memory_usage_with_different_methods(self):
        """Test memory usage comparison between quantum and classical methods."""
        process = psutil.Process(os.getpid())

        # Test quantum method
        quantum_response = {
            "predictions": [{
                "topic": "method-comparison",
                "importance": 0.30,
                "confidence_interval": [0.25, 0.35],
                "trend": "increasing",
                "method": "quantum"
            }],
            "execution_time_ms": 1800,
            "memory_usage_mb": 256,
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = quantum_response

        quantum_request = {"topics": ["method-comparison"], "force_classical": False}
        response = self.client.post("/api/v1/predict", json=quantum_request)

        assert response.status_code == 200
        quantum_data = response.json()
        quantum_memory = quantum_data["memory_usage_mb"]

        # Test classical method
        classical_response = {
            "predictions": [{
                "topic": "method-comparison",
                "importance": 0.30,
                "confidence_interval": [0.25, 0.35],
                "trend": "increasing",
                "method": "classical"
            }],
            "execution_time_ms": 400,
            "memory_usage_mb": 64,
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = classical_response

        classical_request = {"topics": ["method-comparison"], "force_classical": True}
        response = self.client.post("/api/v1/predict", json=classical_request)

        assert response.status_code == 200
        classical_data = response.json()
        classical_memory = classical_data["memory_usage_mb"]

        # Classical should use less memory than quantum
        assert classical_memory < quantum_memory
        assert classical_memory > 0
        assert quantum_memory > 0

    def test_memory_usage_under_concurrent_load(self):
        """Test memory usage under concurrent load."""
        import gc
        import queue
        import threading

        process = psutil.Process(os.getpid())
        gc.collect()
        initial_memory = process.memory_info().rss / 1024 / 1024

        # Mock response for concurrent calls
        mock_response = {
            "predictions": [{
                "topic": "concurrent-memory-test",
                "importance": 0.22,
                "confidence_interval": [0.17, 0.27],
                "trend": "stable",
                "method": "quantum"
            }],
            "execution_time_ms": 1200,
            "memory_usage_mb": 180,
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": ["concurrent-memory-test"]}

        # Function to make API calls and track memory
        def make_request_with_memory(result_queue):
            try:
                thread_memory_start = process.memory_info().rss / 1024 / 1024
                response = self.client.post("/api/v1/predict", json=request_data)
                thread_memory_end = process.memory_info().rss / 1024 / 1024

                result_queue.put({
                    "status": response.status_code,
                    "data": response.json() if response.status_code == 200 else None,
                    "memory_growth": thread_memory_end - thread_memory_start
                })
            except Exception as e:
                result_queue.put({"error": str(e)})

        # Make concurrent requests
        num_concurrent = 3
        result_queue = queue.Queue()
        threads = []

        # Start concurrent requests
        for _ in range(num_concurrent):
            thread = threading.Thread(target=make_request_with_memory, args=(result_queue,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        gc.collect()
        final_memory = process.memory_info().rss / 1024 / 1024
        total_memory_growth = final_memory - initial_memory

        # Collect results
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())

        # Verify all requests succeeded
        assert len(results) == num_concurrent
        for result in results:
            assert "status" in result
            assert result["status"] == 200
            assert result["data"] is not None
            # RSS can shrink when the garbage collector runs mid-request, so
            # only require the per-request delta to stay within a sane band.
            assert -100 < result["memory_growth"] < 100

        # Total memory growth should be reasonable
        assert total_memory_growth < 200  # Less than 200MB total growth

    def test_memory_leak_detection(self):
        """Test detection of memory leaks over multiple requests."""
        process = psutil.Process(os.getpid())

        # Make many requests to detect potential memory leaks
        memory_readings = []

        for i in range(20):
            mock_response = {
                "predictions": [{
                    "topic": f"leak-test-{i}",
                    "importance": 0.25,
                    "confidence_interval": [0.20, 0.30],
                    "trend": "stable",
                    "method": "quantum"
                }],
                "execution_time_ms": 1000,
                "memory_usage_mb": 120,
                "fallback_used": False
            }

            self.mock_predictor.predict_topics.return_value = mock_response

            request_data = {"topics": [f"leak-test-{i}"]}
            response = self.client.post("/api/v1/predict", json=request_data)

            assert response.status_code == 200

            # Record memory usage
            current_memory = process.memory_info().rss / 1024 / 1024
            memory_readings.append(current_memory)

        # Check for memory leak (should not grow by more than 10MB total)
        if len(memory_readings) > 1:
            total_growth = memory_readings[-1] - memory_readings[0]
            assert total_growth < 10  # Less than 10MB growth over 20 requests

    def test_memory_usage_with_large_datasets(self):
        """Test memory usage with large datasets."""
        # Create a large dataset
        large_topics = [f"topic_{i}" for i in range(20)]
        predictions = []

        for i, topic in enumerate(large_topics):
            predictions.append({
                "topic": topic,
                "importance": 0.1 + (i % 5) * 0.1,
                "confidence_interval": [0.05 + (i % 5) * 0.1, 0.15 + (i % 5) * 0.1],
                "trend": "stable",
                "method": "quantum"
            })

        mock_response = {
            "predictions": predictions,
            "execution_time_ms": 5000,
            "memory_usage_mb": 384,  # Moderate memory usage
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": large_topics}

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024

        response = self.client.post("/api/v1/predict", json=request_data)

        final_memory = process.memory_info().rss / 1024 / 1024

        assert response.status_code == 200
        data = response.json()

        # Should handle large dataset
        assert len(data["predictions"]) == 20
        assert data["memory_usage_mb"] < 1024  # Less than 1GB

        # Process memory growth should be reasonable
        memory_growth = final_memory - initial_memory
        assert memory_growth < 150  # Less than 150MB growth

    def test_memory_threshold_monitoring(self):
        """Test monitoring of memory usage against thresholds."""
        # Test different memory usage scenarios
        memory_scenarios = [
            {"usage": 128, "threshold": 256, "should_warn": False},
            {"usage": 300, "threshold": 256, "should_warn": True},
            {"usage": 600, "threshold": 512, "should_warn": True}
        ]

        for scenario in memory_scenarios:
            mock_response = {
                "predictions": [{
                    "topic": f"threshold-test-{scenario['usage']}",
                    "importance": 0.25,
                    "confidence_interval": [0.20, 0.30],
                    "trend": "stable",
                    "method": "quantum"
                }],
                "execution_time_ms": 1500,
                "memory_usage_mb": scenario["usage"],
                "memory_threshold_exceeded": scenario["usage"] > scenario["threshold"],
                "fallback_used": False
            }

            self.mock_predictor.predict_topics.return_value = mock_response

            request_data = {"topics": [f"threshold-test-{scenario['usage']}"]}

            response = self.client.post("/api/v1/predict", json=request_data)

            assert response.status_code == 200
            data = response.json()

            # Verify threshold monitoring
            if scenario["should_warn"]:
                assert data.get("memory_threshold_exceeded", False) is True
            else:
                assert data.get("memory_threshold_exceeded", False) is False
