import React, { useState } from 'react';
import { Container, Row, Col, Card, Form, Button, Alert, Badge } from 'react-bootstrap';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../services/api';

const CreateReport: React.FC = () => {
    const [formData, setFormData] = useState({
        title: '',
        description: '',
        topics: [] as string[],
        prediction_year: '',
        confidence_threshold: 0.8
    });
    const [currentTopic, setCurrentTopic] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const navigate = useNavigate();

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: name === 'confidence_threshold' ? parseFloat(value) : value
        }));
    };

    const handleAddTopic = () => {
        if (currentTopic.trim() && !formData.topics.includes(currentTopic.trim())) {
            setFormData(prev => ({
                ...prev,
                topics: [...prev.topics, currentTopic.trim()]
            }));
            setCurrentTopic('');
        }
    };

    const handleRemoveTopic = (topicToRemove: string) => {
        setFormData(prev => ({
            ...prev,
            topics: prev.topics.filter(topic => topic !== topicToRemove)
        }));
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleAddTopic();
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (!formData.title.trim()) {
            setError('Title is required');
            return;
        }

        if (!formData.description.trim()) {
            setError('Description is required');
            return;
        }

        if (formData.topics.length === 0) {
            setError('At least one topic is required');
            return;
        }

        setLoading(true);

        try {
            const reportData = {
                title: formData.title,
                description: formData.description,
                topics: formData.topics,
                prediction_year: formData.prediction_year ? parseInt(formData.prediction_year) : undefined,
                confidence_threshold: formData.confidence_threshold
            };

            const report = await apiClient.createReport(reportData);
            navigate(`/reports/${report.id}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create report');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Container>
            <div className="mb-4">
                <h1 className="mb-2">📝 Create New Report</h1>
                <p className="text-muted">Generate predictions for exam topics using quantum-classical hybrid analysis</p>
            </div>

            <Row className="justify-content-center">
                <Col lg={8}>
                    <Card>
                        <Card.Body className="p-4">
                            {error && (
                                <Alert variant="danger" className="mb-4">
                                    {error}
                                </Alert>
                            )}

                            <Form onSubmit={handleSubmit}>
                                <Form.Group className="mb-4">
                                    <Form.Label>Report Title *</Form.Label>
                                    <Form.Control
                                        type="text"
                                        name="title"
                                        value={formData.title}
                                        onChange={handleInputChange}
                                        placeholder="Enter a descriptive title for your report"
                                        required
                                    />
                                    <Form.Text className="text-muted">
                                        Choose a clear, descriptive title that explains what this report analyzes.
                                    </Form.Text>
                                </Form.Group>

                                <Form.Group className="mb-4">
                                    <Form.Label>Description *</Form.Label>
                                    <Form.Control
                                        as="textarea"
                                        rows={3}
                                        name="description"
                                        value={formData.description}
                                        onChange={handleInputChange}
                                        placeholder="Describe the purpose and scope of this analysis"
                                        required
                                    />
                                    <Form.Text className="text-muted">
                                        Provide context about what questions this report will help answer.
                                    </Form.Text>
                                </Form.Group>

                                <Form.Group className="mb-4">
                                    <Form.Label>Topics to Analyze *</Form.Label>
                                    <div className="d-flex mb-2">
                                        <Form.Control
                                            type="text"
                                            value={currentTopic}
                                            onChange={(e) => setCurrentTopic(e.target.value)}
                                            onKeyPress={handleKeyPress}
                                            placeholder="Enter a topic (e.g., quantum mechanics, algorithms)"
                                            className="me-2"
                                        />
                                        <Button
                                            variant="outline-primary"
                                            onClick={handleAddTopic}
                                            disabled={!currentTopic.trim()}
                                        >
                                            Add Topic
                                        </Button>
                                    </div>

                                    {formData.topics.length > 0 && (
                                        <div className="mt-3">
                                            <p className="text-muted small mb-2">Selected Topics:</p>
                                            <div className="d-flex flex-wrap gap-2">
                                                {formData.topics.map((topic, index) => (
                                                    <Badge
                                                        key={index}
                                                        bg="primary"
                                                        className="d-flex align-items-center"
                                                        style={{ cursor: 'pointer' }}
                                                        onClick={() => handleRemoveTopic(topic)}
                                                    >
                                                        {topic} ×
                                                    </Badge>
                                                ))}
                                            </div>
                                            <Form.Text className="text-muted">
                                                Click on a topic badge to remove it.
                                            </Form.Text>
                                        </div>
                                    )}
                                </Form.Group>

                                <Row>
                                    <Col md={6}>
                                        <Form.Group className="mb-4">
                                            <Form.Label>Prediction Year (Optional)</Form.Label>
                                            <Form.Control
                                                type="number"
                                                name="prediction_year"
                                                value={formData.prediction_year}
                                                onChange={handleInputChange}
                                                placeholder="2025"
                                                min="2020"
                                                max="2030"
                                            />
                                            <Form.Text className="text-muted">
                                                Year to predict for. Leave empty to use current year + 1.
                                            </Form.Text>
                                        </Form.Group>
                                    </Col>

                                    <Col md={6}>
                                        <Form.Group className="mb-4">
                                            <Form.Label>Confidence Threshold</Form.Label>
                                            <Form.Control
                                                type="number"
                                                name="confidence_threshold"
                                                value={formData.confidence_threshold}
                                                onChange={handleInputChange}
                                                step="0.1"
                                                min="0.1"
                                                max="1.0"
                                            />
                                            <Form.Text className="text-muted">
                                                Minimum confidence level for predictions (0.1 - 1.0).
                                            </Form.Text>
                                        </Form.Group>
                                    </Col>
                                </Row>

                                <div className="d-flex gap-3">
                                    <Button
                                        variant="primary"
                                        type="submit"
                                        size="lg"
                                        disabled={loading}
                                        className="flex-fill"
                                    >
                                        {loading ? (
                                            <>
                                                <span className="loading-spinner me-2"></span>
                                                Creating Report...
                                            </>
                                        ) : (
                                            'Create Report'
                                        )}
                                    </Button>

                                    <Button
                                        variant="outline-secondary"
                                        size="lg"
                                        onClick={() => navigate('/')}
                                    >
                                        Cancel
                                    </Button>
                                </div>
                            </Form>
                        </Card.Body>
                    </Card>
                </Col>
            </Row>
        </Container>
    );
};

export default CreateReport;
