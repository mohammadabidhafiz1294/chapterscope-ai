"""VQE Predictor service for quantum-classical hybrid predictions."""

import time
import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass

from src.config import service_logger, settings

# Import Qiskit components (will be installed)
try:
    from qiskit import QuantumCircuit
    # Note: VQE and COBYLA from qiskit.algorithms are deprecated in Qiskit 2.x
    # We'll implement custom VQE using StatevectorEstimator and scipy optimization
    from qiskit.primitives import StatevectorEstimator
    from qiskit.quantum_info import SparsePauliOp
    from qiskit_aer import AerSimulator
    from qiskit.circuit.library import TwoLocal
    from scipy.optimize import minimize
    import numpy as np

    QISKIT_AVAILABLE = True
    service_logger.info("Qiskit available for quantum predictions (using updated API)")
except ImportError as e:
    # Define dummy classes to avoid import errors
    QuantumCircuit = None
    StatevectorEstimator = None
    SparsePauliOp = None
    AerSimulator = None
    TwoLocal = None

    QISKIT_AVAILABLE = False
    service_logger.warning(
        "Qiskit not available, using mock implementation",
        error=str(e)
    )


@dataclass
class PredictionRequest:
    """Request for topic prediction."""

    topics: List[str]
    historical_years: int = 5
    confidence_level: float = 0.95
    force_classical: bool = False


@dataclass
class PredictionResult:
    """Result of a prediction."""

    topic: str
    importance: float
    confidence_interval: Tuple[float, float]
    trend: str
    method: str


@dataclass
class VQEPredictionResponse:
    """Response containing all prediction results."""

    predictions: List[PredictionResult]
    execution_time_ms: int
    fallback_used: bool


class VQEPredictor:
    """Main VQE prediction service."""

    def __init__(self, max_qubits: int = None, max_iterations: int = None):
        """Initialize VQE predictor."""
        self.max_qubits = max_qubits or settings.max_qubits
        self.max_iterations = max_iterations or settings.max_iterations
        self.quantum_available = QISKIT_AVAILABLE and settings.quantum_available

        service_logger.info(
            "VQEPredictor initialized",
            max_qubits=self.max_qubits,
            max_iterations=self.max_iterations,
            quantum_available=self.quantum_available,
        )

    def predict_topics(
        self, request: PredictionRequest, historical_data: Dict[str, List[float]]
    ) -> VQEPredictionResponse:
        """
        Predict topic importance using hybrid quantum-classical approach.

        Args:
            request: Prediction request parameters
            historical_data: Historical frequency data for topics

        Returns:
            Prediction response with results
        """
        start_time = time.time()
        predictions = []

        service_logger.info(
            "Starting topic prediction",
            topics=request.topics,
            historical_years=request.historical_years,
            force_classical=request.force_classical,
        )

        for topic in request.topics:
            if topic not in historical_data:
                service_logger.warning(f"Topic '{topic}' not found in historical data")
                continue

            data = historical_data[topic]

            if len(data) < settings.min_historical_years:
                service_logger.warning(
                    f"Topic '{topic}' has insufficient data",
                    data_points=len(data),
                    required=settings.min_historical_years,
                )
                continue

            try:
                if self.quantum_available and not request.force_classical:
                    result = self._quantum_prediction(
                        topic, data, request.confidence_level
                    )
                    service_logger.info(f"Quantum prediction completed for {topic}")
                else:
                    result = self._classical_prediction(
                        topic, data, request.confidence_level
                    )
                    service_logger.info(f"Classical prediction completed for {topic}")

                predictions.append(result)

            except Exception as e:
                service_logger.error(
                    f"Error predicting {topic}", error=str(e), exc_info=True
                )
                # Fallback to classical method
                try:
                    result = self._classical_prediction(
                        topic, data, request.confidence_level
                    )
                    result.method = "classical_fallback"
                    predictions.append(result)
                    service_logger.info(f"Classical fallback successful for {topic}")
                except Exception as e2:
                    service_logger.error(
                        f"Classical fallback also failed for {topic}",
                        error=str(e2),
                        exc_info=True,
                    )

        execution_time = int((time.time() - start_time) * 1000)
        fallback_used = any(
            p.method in ["classical", "classical_fallback"] for p in predictions
        )

        return VQEPredictionResponse(
            predictions=predictions,
            execution_time_ms=execution_time,
            fallback_used=fallback_used,
        )

    def _quantum_prediction(
        self, topic: str, data: List[float], confidence_level: float
    ) -> PredictionResult:
        """Perform quantum prediction using VQE."""
        if not self.quantum_available:
            raise RuntimeError("Quantum prediction requested but Qiskit not available")

        service_logger.info(f"Starting quantum prediction for {topic}")

        # Create Hamiltonian based on historical data patterns
        num_qubits = min(len(data), self.max_qubits)

        # Create a more sophisticated Hamiltonian based on data correlations
        pauli_list = []

        # Add identity term with base energy
        base_energy = np.mean(data) / 100.0  # Normalize to 0-1 range
        pauli_list.append(("I" * num_qubits, base_energy))

        # Add Z terms based on data trends
        for i in range(num_qubits):
            if i < len(data):
                weight = data[i] / 100.0
                pauli_str = "I" * num_qubits
                pauli_list.append(
                    (pauli_str[:i] + "Z" + pauli_str[i + 1 :], weight * 0.1)
                )

        # Add ZZ interaction terms for correlations
        for i in range(num_qubits - 1):
            for j in range(i + 1, num_qubits):
                if i < len(data) and j < len(data):
                    correlation = (
                        np.corrcoef([data[i]], [data[j]])[0, 1] if len(data) > 1 else 0
                    )
                    pauli_str = "I" * num_qubits
                    pauli_list.append(
                        (
                            pauli_str[:i]
                            + "Z"
                            + pauli_str[i + 1 : j]
                            + "Z"
                            + pauli_str[j + 1 :],
                            correlation * 0.05,
                        )
                    )

        hamiltonian = SparsePauliOp.from_list(pauli_list)

        # Create parameterized quantum circuit (ansatz)
        ansatz = QuantumCircuit(num_qubits)
        for i in range(num_qubits):
            ansatz.ry(np.pi / 4 * (i + 1), i)  # Initial rotation

        # Add entanglement layers
        for layer in range(2):
            for i in range(num_qubits - 1):
                ansatz.cx(i, i + 1)
            for i in range(num_qubits):
                ansatz.ry(np.pi / 3 * (layer + 1), i)

        # Setup custom VQE implementation using StatevectorEstimator and scipy
        estimator = StatevectorEstimator()

        def objective_function(params):
            """Objective function for VQE optimization."""
            try:
                bound_circuit = ansatz.bind_parameters(params)
                pub = (bound_circuit, hamiltonian)
                job = estimator.run([pub])
                result = job.result()
                energy = result[0].data.evs[0]
                return float(energy.real)
            except Exception as e:
                service_logger.warning(f"Error in VQE objective function: {e}")
                return 1000.0  # High penalty for errors

        # Run custom VQE using scipy optimization
        service_logger.debug(f"Running custom VQE for {topic} with {num_qubits} qubits")
        initial_params = np.random.uniform(0, 2*np.pi, ansatz.num_parameters)
        
        result = minimize(
            objective_function,
            initial_params,
            method='COBYLA',
            options={'maxiter': self.max_iterations}
        )

        # Convert minimum energy to importance score (0-1 range)
        eigenvalue = result.fun
        importance = (eigenvalue + 2.0) / 4.0  # Scale to 0-1 range
        importance = max(0.0, min(1.0, importance))

        service_logger.info(
            f"Quantum prediction completed for {topic}",
            eigenvalue=result.eigenvalue.real,
            importance=importance,
        )

        # Calculate confidence interval based on optimizer convergence
        std_dev = np.std(data) / len(data) if len(data) > 1 else 0.1
        margin = (1.96 * std_dev) * (
            1 - confidence_level
        )  # Adjust for confidence level
        confidence_lower = max(0.0, importance - margin)
        confidence_upper = min(1.0, importance + margin)

        # Determine trend from data
        if len(data) >= 2:
            trend = "increasing" if data[-1] > data[-2] else "decreasing"
        else:
            trend = "stable"

        return PredictionResult(
            topic=topic,
            importance=round(importance, 4),
            confidence_interval=(
                round(confidence_lower, 4),
                round(confidence_upper, 4),
            ),
            trend=trend,
            method="quantum",
        )

    def _classical_prediction(
        self, topic: str, data: List[float], confidence_level: float
    ) -> PredictionResult:
        """Perform classical prediction using simple statistical methods."""
        if len(data) < 2:
            raise ValueError("Need at least 2 data points for classical prediction")

        # Simple linear trend prediction
        x = np.arange(len(data))
        y = np.array(data)

        # Linear regression
        slope, intercept = np.polyfit(x, y, 1)

        # Predict next value
        next_x = len(data)
        predicted_value = slope * next_x + intercept

        # Normalize to 0-1 range (assuming max frequency is 100)
        importance = min(1.0, max(0.0, predicted_value / 100.0))

        # Calculate confidence interval
        residuals = y - (slope * x + intercept)
        std_error = np.std(residuals, ddof=2)
        margin = 1.96 * std_error  # 95% confidence
        confidence_lower = max(0.0, (predicted_value - margin) / 100.0)
        confidence_upper = min(1.0, (predicted_value + margin) / 100.0)

        # Determine trend
        trend = "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable"

        return PredictionResult(
            topic=topic,
            importance=round(importance, 4),
            confidence_interval=(
                round(confidence_lower, 4),
                round(confidence_upper, 4),
            ),
            trend=trend,
            method="classical",
        )
