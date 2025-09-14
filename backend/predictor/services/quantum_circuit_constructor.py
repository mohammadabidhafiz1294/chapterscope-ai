"""Quantum circuit constructor for topic relationship modeling."""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.circuit import Parameter
from qiskit.quantum_info import SparsePauliOp
from qiskit.circuit.library import RYGate, RZGate, CXGate, CZGate

logger = logging.getLogger(__name__)


@dataclass
class QuantumCircuitConfig:
    """Configuration for quantum circuit construction."""
    num_qubits: int
    num_layers: int
    entanglement_pattern: str  # 'full', 'linear', 'circular'
    rotation_gates: List[str]  # ['ry', 'rz']
    entanglement_gates: List[str]  # ['cz', 'cx']
    include_bias: bool = True


@dataclass
class TopicEncoding:
    """Encoding of topics into quantum states."""
    topic: str
    qubit_index: int
    amplitude: float
    phase: float


@dataclass
class HamiltonianConstruction:
    """Result of Hamiltonian construction."""
    hamiltonian: SparsePauliOp
    topic_mappings: Dict[str, int]
    energy_scale: float
    construction_time: float


class QuantumCircuitConstructor:
    """Service for constructing quantum circuits for topic relationship modeling."""

    def __init__(self, config: Optional[QuantumCircuitConfig] = None):
        """Initialize quantum circuit constructor."""
        self.config = config or QuantumCircuitConfig(
            num_qubits=8,
            num_layers=3,
            entanglement_pattern='full',
            rotation_gates=['ry', 'rz'],
            entanglement_gates=['cz']
        )

        logger.info(f"QuantumCircuitConstructor initialized with {self.config.num_qubits} qubits")

    def construct_topic_circuit(self, topics: List[str],
                               topic_frequencies: Dict[str, float],
                               topic_relationships: List[Tuple[str, str, float]]) -> QuantumCircuit:
        """
        Construct a quantum circuit encoding topic relationships.

        Args:
            topics: List of topics to encode
            topic_frequencies: Frequency of each topic
            topic_relationships: Relationships between topics (topic_a, topic_b, strength)

        Returns:
            Quantum circuit encoding topic relationships
        """
        # Limit to available qubits
        num_topics = min(len(topics), self.config.num_qubits)
        selected_topics = topics[:num_topics]

        # Create quantum circuit
        qr = QuantumRegister(self.config.num_qubits, 'q')
        cr = ClassicalRegister(self.config.num_qubits, 'c')
        circuit = QuantumCircuit(qr, cr)

        # Encode topic frequencies as initial amplitudes
        self._encode_topic_frequencies(circuit, selected_topics, topic_frequencies)

        # Add variational layers
        for layer in range(self.config.num_layers):
            self._add_variational_layer(circuit, layer)

        # Add final measurements
        circuit.measure(qr, cr)

        logger.info(f"Constructed quantum circuit with {circuit.num_qubits} qubits and {circuit.depth()} depth")
        return circuit

    def _encode_topic_frequencies(self, circuit: QuantumCircuit,
                                topics: List[str],
                                topic_frequencies: Dict[str, float]):
        """Encode topic frequencies as quantum amplitudes."""
        for i, topic in enumerate(topics):
            if i >= self.config.num_qubits:
                break

            frequency = topic_frequencies.get(topic, 0.0)
            # Normalize frequency to angle
            angle = np.pi * (frequency / 100.0)  # Assuming frequency is percentage

            # Apply rotation to encode frequency
            circuit.ry(angle, i)

            # Add phase encoding for additional information
            phase = np.pi * (i / len(topics))  # Phase based on topic position
            circuit.rz(phase, i)

    def _add_variational_layer(self, circuit: QuantumCircuit, layer_index: int):
        """Add a variational layer to the circuit."""
        num_qubits = circuit.num_qubits

        # Add rotation gates
        for qubit in range(num_qubits):
            for gate_type in self.config.rotation_gates:
                param = Parameter(f'{gate_type}_{layer_index}_{qubit}')
                if gate_type == 'ry':
                    circuit.ry(param, qubit)
                elif gate_type == 'rz':
                    circuit.rz(param, qubit)

        # Add entanglement
        if self.config.entanglement_pattern == 'full':
            self._add_full_entanglement(circuit, layer_index)
        elif self.config.entanglement_pattern == 'linear':
            self._add_linear_entanglement(circuit, layer_index)
        elif self.config.entanglement_pattern == 'circular':
            self._add_circular_entanglement(circuit, layer_index)

    def _add_full_entanglement(self, circuit: QuantumCircuit, layer_index: int):
        """Add full entanglement between all qubits."""
        num_qubits = circuit.num_qubits

        for i in range(num_qubits):
            for j in range(i + 1, num_qubits):
                for gate_type in self.config.entanglement_gates:
                    if gate_type == 'cz':
                        circuit.cz(i, j)
                    elif gate_type == 'cx':
                        circuit.cx(i, j)

    def _add_linear_entanglement(self, circuit: QuantumCircuit, layer_index: int):
        """Add linear entanglement pattern."""
        num_qubits = circuit.num_qubits

        for i in range(num_qubits - 1):
            for gate_type in self.config.entanglement_gates:
                if gate_type == 'cz':
                    circuit.cz(i, i + 1)
                elif gate_type == 'cx':
                    circuit.cx(i, i + 1)

    def _add_circular_entanglement(self, circuit: QuantumCircuit, layer_index: int):
        """Add circular entanglement pattern."""
        num_qubits = circuit.num_qubits

        for i in range(num_qubits):
            next_qubit = (i + 1) % num_qubits
            for gate_type in self.config.entanglement_gates:
                if gate_type == 'cz':
                    circuit.cz(i, next_qubit)
                elif gate_type == 'cx':
                    circuit.cx(i, next_qubit)

    def construct_hamiltonian(self, topics: List[str],
                            topic_frequencies: Dict[str, float],
                            topic_relationships: List[Tuple[str, str, float]]) -> HamiltonianConstruction:
        """
        Construct Hamiltonian for topic relationship optimization.

        Args:
            topics: List of topics
            topic_frequencies: Topic frequency data
            topic_relationships: Topic relationship data

        Returns:
            HamiltonianConstruction result
        """
        import time
        start_time = time.time()

        # Map topics to qubits
        topic_mappings = {}
        for i, topic in enumerate(topics[:self.config.num_qubits]):
            topic_mappings[topic] = i

        hamiltonian_terms = []

        # Add frequency-based terms
        for topic, qubit in topic_mappings.items():
            frequency = topic_frequencies.get(topic, 0.0)
            # Cost term: prefer topics with higher frequencies
            coefficient = -frequency / 100.0  # Negative for minimization

            pauli_string = 'I' * self.config.num_qubits
            pauli_list = list(pauli_string)
            pauli_list[qubit] = 'Z'
            pauli_string = ''.join(pauli_list)

            hamiltonian_terms.append((pauli_string, coefficient))

        # Add relationship-based terms
        for topic_a, topic_b, strength in topic_relationships:
            if topic_a in topic_mappings and topic_b in topic_mappings:
                qubit_a = topic_mappings[topic_a]
                qubit_b = topic_mappings[topic_b]

                # Coupling term based on relationship strength
                coefficient = strength

                pauli_string = 'I' * self.config.num_qubits
                pauli_list = list(pauli_string)
                pauli_list[qubit_a] = 'Z'
                pauli_list[qubit_b] = 'Z'
                pauli_string = ''.join(pauli_list)

                hamiltonian_terms.append((pauli_string, coefficient))

        # Add bias term if configured
        if self.config.include_bias:
            bias_coefficient = 0.1  # Small bias to avoid trivial solutions
            hamiltonian_terms.append(('I' * self.config.num_qubits, bias_coefficient))

        # Construct SparsePauliOp
        if hamiltonian_terms:
            pauli_list = [term[0] for term in hamiltonian_terms]
            coeffs = [term[1] for term in hamiltonian_terms]
            hamiltonian = SparsePauliOp(pauli_list, coeffs)
        else:
            # Fallback Hamiltonian
            hamiltonian = SparsePauliOp(['I' * self.config.num_qubits], [1.0])

        # Calculate energy scale
        energy_scale = np.sqrt(sum(coeff**2 for _, coeff in hamiltonian_terms))

        construction_time = time.time() - start_time

        logger.info(f"Constructed Hamiltonian with {len(hamiltonian_terms)} terms in {construction_time:.3f}s")

        return HamiltonianConstruction(
            hamiltonian=hamiltonian,
            topic_mappings=topic_mappings,
            energy_scale=energy_scale,
            construction_time=construction_time
        )

    def create_ansatz_circuit(self, num_parameters: Optional[int] = None) -> QuantumCircuit:
        """
        Create a parameterized ansatz circuit for VQE.

        Args:
            num_parameters: Number of parameters (optional)

        Returns:
            Parameterized quantum circuit
        """
        qr = QuantumRegister(self.config.num_qubits, 'q')
        circuit = QuantumCircuit(qr)

        # Add variational layers
        for layer in range(self.config.num_layers):
            self._add_variational_layer(circuit, layer)

        logger.info(f"Created ansatz circuit with {circuit.num_parameters} parameters")
        return circuit

    def encode_topic_data(self, topic_data: Dict[str, Any]) -> List[TopicEncoding]:
        """
        Encode topic data into quantum states.

        Args:
            topic_data: Dictionary of topic information

        Returns:
            List of topic encodings
        """
        encodings = []

        for i, (topic, data) in enumerate(topic_data.items()):
            if i >= self.config.num_qubits:
                break

            # Extract frequency and other metrics
            frequency = data.get('frequency', 0.0)
            trend = data.get('trend', 0.0)

            # Calculate amplitude and phase
            amplitude = np.sqrt(frequency / 100.0)  # Normalize to [0, 1]
            phase = np.pi * trend  # Trend affects phase

            encoding = TopicEncoding(
                topic=topic,
                qubit_index=i,
                amplitude=amplitude,
                phase=phase
            )
            encodings.append(encoding)

        logger.info(f"Encoded {len(encodings)} topics into quantum states")
        return encodings

    def get_circuit_properties(self, circuit: QuantumCircuit) -> Dict[str, Any]:
        """Get properties of a quantum circuit."""
        return {
            'num_qubits': circuit.num_qubits,
            'depth': circuit.depth(),
            'num_parameters': circuit.num_parameters,
            'gate_counts': circuit.count_ops(),
            'circuit_size': len(circuit),
            'entanglement_layers': self.config.num_layers
        }

    def optimize_circuit_depth(self, target_depth: int) -> QuantumCircuitConfig:
        """Optimize circuit configuration for target depth."""
        optimized_config = QuantumCircuitConfig(
            num_qubits=self.config.num_qubits,
            num_layers=min(target_depth // 2, self.config.num_layers),
            entanglement_pattern=self.config.entanglement_pattern,
            rotation_gates=self.config.rotation_gates,
            entanglement_gates=self.config.entanglement_gates,
            include_bias=self.config.include_bias
        )

        logger.info(f"Optimized circuit config for depth {target_depth}")
        return optimized_config

    def validate_circuit(self, circuit: QuantumCircuit) -> Dict[str, Any]:
        """Validate quantum circuit for correctness."""
        validation = {
            'is_valid': True,
            'issues': [],
            'warnings': [],
            'recommendations': []
        }

        # Check qubit count
        if circuit.num_qubits > 20:
            validation['warnings'].append('High qubit count may affect simulation performance')

        # Check circuit depth
        if circuit.depth() > 100:
            validation['warnings'].append('Deep circuit may be difficult to optimize')

        # Check parameter count
        if circuit.num_parameters > 50:
            validation['warnings'].append('High parameter count may slow optimization')

        # Check for isolated qubits
        gate_counts = circuit.count_ops()
        if 'barrier' in gate_counts or circuit.depth() < 2:
            validation['issues'].append('Circuit may have isolated qubits')

        # Recommendations
        if circuit.num_parameters == 0:
            validation['recommendations'].append('Add parameters for variational optimization')

        if not any(gate in gate_counts for gate in ['cx', 'cz', 'cnot']):
            validation['recommendations'].append('Add entanglement gates for quantum advantage')

        return validation
