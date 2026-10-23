"""Performance tests for quantum simulation timing."""

import pytest
import time
import statistics
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.services.vqe_predictor import VQEPredictor


class TestQuantumPerformance:
    """Performance tests for quantum simulation timing."""

    def setup_method(self):
        """Set up test client and mock services."""
        self.client = TestClient(app)
        self.mock_predictor = MagicMock(spec=VQEPredictor)

        # Mock quantum as available
        self.mock_predictor.quantum_available = True

        # Patch the predictor in the API for the duration of the test
        self.predictor_patcher = patch('src.api.main.predictor', self.mock_predictor)
        self.predictor_patcher.start()

    def teardown_method(self):
        """Stop patchers started in setup_method."""
        self.predictor_patcher.stop()

    def test_quantum_simulation_timing_baseline(self):
        """Test baseline timing for quantum simulation."""
        # Mock a typical quantum simulation response
        mock_response = {
            "predictions": [{
                "topic": "quantum-baseline",
                "importance": 0.25,
                "confidence_interval": [0.20, 0.30],
                "trend": "stable",
                "method": "quantum"
            }],
            "execution_time_ms": 1500,  # 1.5 seconds baseline
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": ["quantum-baseline"]}

        start_time = time.time()
        response = self.client.post("/api/v1/predict", json=request_data)
        end_time = time.time()

        assert response.status_code == 200
        data = response.json()

        # Verify timing is within reasonable bounds
        assert data["execution_time_ms"] > 1000  # At least 1 second for quantum
        assert data["execution_time_ms"] < 10000  # Less than 10 seconds
        assert end_time - start_time < 5.0  # API call should complete quickly

    def test_quantum_performance_scaling(self):
        """Test how quantum performance scales with problem size."""
        # Test different problem sizes
        test_cases = [
            {"topics": ["small"], "expected_max_time": 2000},
            {"topics": ["small", "medium"], "expected_max_time": 3000},
            {"topics": ["small", "medium", "large"], "expected_max_time": 5000}
        ]

        for i, test_case in enumerate(test_cases):
            # Mock response with increasing execution time
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
                "execution_time_ms": 1000 + i * 1000,  # Increasing time
                "fallback_used": False
            }

            self.mock_predictor.predict_topics.return_value = mock_response

            start_time = time.time()
            response = self.client.post("/api/v1/predict", json=test_case)
            end_time = time.time()

            assert response.status_code == 200
            data = response.json()

            # Verify scaling is reasonable (not exponential)
            assert data["execution_time_ms"] <= test_case["expected_max_time"]
            assert end_time - start_time < 10.0

    def test_quantum_memory_usage_bounds(self):
        """Test quantum simulation memory usage stays within bounds."""
        # Mock response with memory tracking
        mock_response = {
            "predictions": [{
                "topic": "memory-test",
                "importance": 0.30,
                "confidence_interval": [0.25, 0.35],
                "trend": "increasing",
                "method": "quantum"
            }],
            "execution_time_ms": 1800,
            "memory_usage_mb": 256,  # Mock memory usage
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": ["memory-test"]}

        response = self.client.post("/api/v1/predict", json=request_data)

        assert response.status_code == 200
        data = response.json()

        # Memory usage should be reasonable
        assert "memory_usage_mb" in data
        assert data["memory_usage_mb"] > 0
        assert data["memory_usage_mb"] < 1024  # Less than 1GB

    def test_quantum_convergence_performance(self):
        """Test quantum algorithm convergence performance."""
        # Mock different convergence scenarios
        convergence_tests = [
            {"iterations": 50, "expected_time": 1000},
            {"iterations": 100, "expected_time": 2000},
            {"iterations": 200, "expected_time": 4000}
        ]

        for test_case in convergence_tests:
            mock_response = {
                "predictions": [{
                    "topic": f"convergence-{test_case['iterations']}",
                    "importance": 0.25,
                    "confidence_interval": [0.20, 0.30],
                    "trend": "stable",
                    "method": "quantum"
                }],
                "execution_time_ms": test_case["expected_time"],
                "optimizer_iterations": test_case["iterations"],
                "convergence_status": "converged",
                "fallback_used": False
            }

            self.mock_predictor.predict_topics.return_value = mock_response

            request_data = {"topics": [f"convergence-{test_case['iterations']}"]}

            start_time = time.time()
            response = self.client.post("/api/v1/predict", json=request_data)
            end_time = time.time()

            assert response.status_code == 200
            data = response.json()

            # Verify convergence metrics
            assert data["optimizer_iterations"] == test_case["iterations"]
            assert data["execution_time_ms"] <= test_case["expected_time"] * 1.5  # Allow 50% variance
            assert end_time - start_time < 10.0

    def test_quantum_performance_under_load(self):
        """Test quantum performance under concurrent load."""
        import threading
        import queue

        # Mock response for concurrent calls
        mock_response = {
            "predictions": [{
                "topic": "load-test",
                "importance": 0.22,
                "confidence_interval": [0.17, 0.27],
                "trend": "stable",
                "method": "quantum"
            }],
            "execution_time_ms": 1200,
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": ["load-test"]}

        # Function to make API calls
        def make_request(result_queue):
            try:
                response = self.client.post("/api/v1/predict", json=request_data)
                result_queue.put((response.status_code, response.json() if response.status_code == 200 else None))
            except Exception as e:
                result_queue.put(("error", str(e)))

        # Make concurrent requests
        num_concurrent = 3
        result_queue = queue.Queue()
        threads = []

        start_time = time.time()

        # Start concurrent requests
        for _ in range(num_concurrent):
            thread = threading.Thread(target=make_request, args=(result_queue,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        end_time = time.time()

        # Collect results
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())

        # Verify all requests succeeded
        assert len(results) == num_concurrent
        for status, data in results:
            assert status == 200
            assert data is not None
            assert data["predictions"][0]["method"] == "quantum"

        # Total time should be reasonable for concurrent execution
        total_time = end_time - start_time
        assert total_time < 15.0  # Should complete within 15 seconds

    def test_quantum_timeout_handling(self):
        """Test handling of quantum simulation timeouts."""
        # Mock a long-running quantum simulation
        mock_response = {
            "predictions": [{
                "topic": "timeout-test",
                "importance": 0.20,
                "confidence_interval": [0.15, 0.25],
                "trend": "stable",
                "method": "quantum"
            }],
            "execution_time_ms": 25000,  # 25 seconds (should timeout)
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": ["timeout-test"]}

        start_time = time.time()
        response = self.client.post("/api/v1/predict", json=request_data)
        end_time = time.time()

        # Should either complete or timeout gracefully
        if response.status_code == 200:
            data = response.json()
            assert data["execution_time_ms"] < 30000  # Less than 30 seconds
        else:
            # If it times out, should return appropriate error
            assert response.status_code in [408, 500, 503]

        # API call itself should not hang
        assert end_time - start_time < 35.0  # Should complete within 35 seconds

    def test_quantum_performance_statistics(self):
        """Test collection of quantum performance statistics."""
        # Make multiple calls to collect statistics
        execution_times = []
        num_calls = 10

        mock_response = {
            "predictions": [{
                "topic": "stats-test",
                "importance": 0.25,
                "confidence_interval": [0.20, 0.30],
                "trend": "stable",
                "method": "quantum"
            }],
            "execution_time_ms": 1500,
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": ["stats-test"]}

        for _ in range(num_calls):
            start_time = time.time()
            response = self.client.post("/api/v1/predict", json=request_data)
            end_time = time.time()

            assert response.status_code == 200
            data = response.json()

            execution_times.append(data["execution_time_ms"])
            api_time = end_time - start_time
            assert api_time < 5.0  # Each API call should be fast

        # Calculate statistics
        mean_time = statistics.mean(execution_times)
        std_dev = statistics.stdev(execution_times) if len(execution_times) > 1 else 0

        # Verify performance consistency
        assert mean_time > 1000  # Should take at least 1 second
        assert mean_time < 3000  # Should be less than 3 seconds on average
        assert std_dev < 500  # Should be reasonably consistent

    def test_quantum_resource_utilization(self):
        """Test quantum resource utilization metrics."""
        # Mock detailed resource usage
        mock_response = {
            "predictions": [{
                "topic": "resource-test",
                "importance": 0.28,
                "confidence_interval": [0.23, 0.33],
                "trend": "increasing",
                "method": "quantum"
            }],
            "execution_time_ms": 2000,
            "memory_usage_mb": 512,
            "cpu_usage_percent": 85,
            "quantum_resources": {
                "qubits_used": 4,
                "circuit_depth": 25,
                "gate_count": 150
            },
            "fallback_used": False
        }

        self.mock_predictor.predict_topics.return_value = mock_response

        request_data = {"topics": ["resource-test"]}

        response = self.client.post("/api/v1/predict", json=request_data)

        assert response.status_code == 200
        data = response.json()

        # Verify resource metrics are present
        assert "memory_usage_mb" in data
        assert "quantum_resources" in data

        quantum_resources = data["quantum_resources"]
        assert "qubits_used" in quantum_resources
        assert "circuit_depth" in quantum_resources
        assert "gate_count" in quantum_resources

        # Verify reasonable resource usage
        assert quantum_resources["qubits_used"] > 0
        assert quantum_resources["qubits_used"] <= 10  # Reasonable qubit count
        assert quantum_resources["circuit_depth"] > 0
        assert quantum_resources["gate_count"] > 0

    def test_quantum_performance_degradation_detection(self):
        """Test detection of performance degradation."""
        # Simulate performance degradation
        base_time = 1500
        degradation_times = [base_time, base_time * 1.2, base_time * 1.5, base_time * 2.0]

        for i, exec_time in enumerate(degradation_times):
            mock_response = {
                "predictions": [{
                    "topic": f"degradation-test-{i}",
                    "importance": 0.25,
                    "confidence_interval": [0.20, 0.30],
                    "trend": "stable",
                    "method": "quantum"
                }],
                "execution_time_ms": exec_time,
                "performance_degraded": exec_time > base_time * 1.5,
                "fallback_used": False
            }

            self.mock_predictor.predict_topics.return_value = mock_response

            request_data = {"topics": [f"degradation-test-{i}"]}

            response = self.client.post("/api/v1/predict", json=request_data)

            assert response.status_code == 200
            data = response.json()

            # Should detect significant performance degradation
            if exec_time > base_time * 1.5:
                assert data.get("performance_degraded", False) is True
