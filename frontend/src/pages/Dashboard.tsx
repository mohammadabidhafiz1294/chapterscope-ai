import React, { useState, useEffect } from 'react';
import { Container, Row, Col, Card, Button, Badge, Alert, Spinner } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { apiClient, Report } from '../services/api';

const Dashboard: React.FC = () => {
    const [reports, setReports] = useState<Report[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    useEffect(() => {
        loadReports();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentPage]);

    const loadReports = async () => {
        try {
            setLoading(true);
            const response = await apiClient.getReports(currentPage, 10);
            setReports(response.items);
            setTotalPages(response.pages);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load reports');
        } finally {
            setLoading(false);
        }
    };

    const getStatusBadgeVariant = (status: string) => {
        switch (status) {
            case 'completed': return 'success';
            case 'processing': return 'warning';
            case 'failed': return 'danger';
            default: return 'secondary';
        }
    };

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString();
    };

    if (loading) {
        return (
            <Container className="d-flex justify-content-center align-items-center" style={{ minHeight: '50vh' }}>
                <div className="text-center">
                    <Spinner animation="border" className="mb-3" />
                    <p>Loading reports...</p>
                </div>
            </Container>
        );
    }

    return (
        <Container>
            <div className="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h1 className="mb-2">📊 Reports Dashboard</h1>
                    <p className="text-muted">Manage your prediction reports and analysis</p>
                </div>
                <Link to="/reports/create">
                    <Button variant="primary" size="lg">
                        ➕ Create New Report
                    </Button>
                </Link>
            </div>

            {error && (
                <Alert variant="danger" className="mb-4">
                    {error}
                </Alert>
            )}

            {reports.length === 0 ? (
                <Card className="text-center p-5">
                    <Card.Body>
                        <h3 className="mb-3">No reports yet</h3>
                        <p className="text-muted mb-4">
                            Create your first prediction report to get started with quantum-classical analysis.
                        </p>
                        <Link to="/reports/create">
                            <Button variant="primary" size="lg">
                                Create Your First Report
                            </Button>
                        </Link>
                    </Card.Body>
                </Card>
            ) : (
                <>
                    <Row>
                        {reports.map((report) => (
                            <Col key={report.id} lg={6} className="mb-4">
                                <Card className="h-100">
                                    <Card.Body className="d-flex flex-column">
                                        <div className="d-flex justify-content-between align-items-start mb-3">
                                            <div className="flex-grow-1">
                                                <h5 className="card-title mb-2">{report.title}</h5>
                                                <p className="text-muted small mb-2">{report.description}</p>
                                            </div>
                                            <Badge bg={getStatusBadgeVariant(report.status)} className="ms-2">
                                                {report.status}
                                            </Badge>
                                        </div>

                                        <div className="mb-3">
                                            <div className="d-flex flex-wrap gap-1 mb-2">
                                                {report.topics.slice(0, 3).map((topic, index) => (
                                                    <Badge key={index} bg="light" text="dark" className="small">
                                                        {topic}
                                                    </Badge>
                                                ))}
                                                {report.topics.length > 3 && (
                                                    <Badge bg="light" text="dark" className="small">
                                                        +{report.topics.length - 3} more
                                                    </Badge>
                                                )}
                                            </div>
                                        </div>

                                        <div className="mt-auto">
                                            <div className="d-flex justify-content-between align-items-center text-muted small mb-3">
                                                <span>Created: {formatDate(report.created_at)}</span>
                                                {report.prediction_year && (
                                                    <span>Year: {report.prediction_year}</span>
                                                )}
                                            </div>

                                            <div className="d-flex gap-2">
                                                <Link to={`/reports/${report.id}`} className="flex-fill">
                                                    <Button variant="outline-primary" size="sm" className="w-100">
                                                        View Details
                                                    </Button>
                                                </Link>
                                                {report.status === 'completed' && (
                                                    <Button
                                                        variant="outline-success"
                                                        size="sm"
                                                        onClick={() => {/* Handle export */ }}
                                                    >
                                                        Export
                                                    </Button>
                                                )}
                                            </div>
                                        </div>
                                    </Card.Body>
                                </Card>
                            </Col>
                        ))}
                    </Row>

                    {/* Pagination */}
                    {totalPages > 1 && (
                        <div className="d-flex justify-content-center mt-4">
                            <div className="btn-group">
                                <Button
                                    variant="outline-primary"
                                    disabled={currentPage === 1}
                                    onClick={() => setCurrentPage(currentPage - 1)}
                                >
                                    Previous
                                </Button>
                                <Button variant="outline-primary" disabled>
                                    Page {currentPage} of {totalPages}
                                </Button>
                                <Button
                                    variant="outline-primary"
                                    disabled={currentPage === totalPages}
                                    onClick={() => setCurrentPage(currentPage + 1)}
                                >
                                    Next
                                </Button>
                            </div>
                        </div>
                    )}
                </>
            )}
        </Container>
    );
};

export default Dashboard;
