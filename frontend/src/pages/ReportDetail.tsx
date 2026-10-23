import React, { useState, useEffect } from 'react';
import { Container, Row, Col, Card, Button, Badge, Alert, Spinner, Tabs, Tab, Table } from 'react-bootstrap';
import { useParams, useNavigate } from 'react-router-dom';
import { apiClient, Report, ReportData } from '../services/api';
import { Bar, Line } from 'react-chartjs-2';
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    BarElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    PointElement,
} from 'chart.js';

ChartJS.register(
    CategoryScale,
    LinearScale,
    BarElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    PointElement
);

const ReportDetail: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [report, setReport] = useState<Report | null>(null);
    const [reportData, setReportData] = useState<ReportData[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [generating, setGenerating] = useState(false);

    useEffect(() => {
        if (id) {
            loadReport();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    const loadReport = async () => {
        if (!id) return;

        try {
            setLoading(true);
            const reportResponse = await apiClient.getReport(id);
            setReport(reportResponse);

            if (reportResponse.status === 'completed') {
                const dataResponse = await apiClient.getReportData(id);
                setReportData(dataResponse.items);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load report');
        } finally {
            setLoading(false);
        }
    };

    const handleGenerateReport = async () => {
        if (!id) return;

        try {
            setGenerating(true);
            await apiClient.generateReport(id);
            // Reload report after generation starts
            setTimeout(() => loadReport(), 2000);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start report generation');
        } finally {
            setGenerating(false);
        }
    };

    const handleExport = async (format: 'pdf' | 'csv' | 'json') => {
        if (!id) return;

        try {
            await apiClient.createExport(id, format);
            alert(`Export in ${format.toUpperCase()} format has been initiated. Check the export history for download link.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create export');
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
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    // Chart data preparation
    const getPredictionScoresChartData = () => {
        if (!reportData.length) return null;

        return {
            labels: reportData.map(item => item.topic),
            datasets: [{
                label: 'Prediction Score',
                data: reportData.map(item => item.prediction_score * 100),
                backgroundColor: 'rgba(54, 162, 235, 0.6)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1,
            }]
        };
    };

    const getHistoricalTrendsChartData = () => {
        if (!reportData.length || !reportData[0].historical_data) return null;

        const years = reportData[0].historical_data.map(h => h.year);
        const datasets = reportData.map((item, index) => ({
            label: item.topic,
            data: item.historical_data.map(h => h.percentage),
            borderColor: `hsl(${index * 137.5 % 360}, 70%, 50%)`,
            backgroundColor: `hsl(${index * 137.5 % 360}, 70%, 50%, 0.1)`,
            tension: 0.1,
        }));

        return {
            labels: years,
            datasets
        };
    };

    if (loading) {
        return (
            <Container className="d-flex justify-content-center align-items-center" style={{ minHeight: '50vh' }}>
                <div className="text-center">
                    <Spinner animation="border" className="mb-3" />
                    <p>Loading report...</p>
                </div>
            </Container>
        );
    }

    if (!report) {
        return (
            <Container className="py-5">
                <Alert variant="danger">
                    <h4>Report Not Found</h4>
                    <p>The requested report could not be found.</p>
                    <Button variant="primary" onClick={() => navigate('/')}>
                        Back to Dashboard
                    </Button>
                </Alert>
            </Container>
        );
    }

    return (
        <Container>
            <div className="d-flex justify-content-between align-items-start mb-4">
                <div>
                    <h1 className="mb-2">{report.title}</h1>
                    <p className="text-muted mb-2">{report.description}</p>
                    <div className="d-flex align-items-center gap-3">
                        <Badge bg={getStatusBadgeVariant(report.status)} className="fs-6">
                            {report.status}
                        </Badge>
                        <small className="text-muted">
                            Created: {formatDate(report.created_at)}
                        </small>
                        {report.prediction_year && (
                            <small className="text-muted">
                                Prediction Year: {report.prediction_year}
                            </small>
                        )}
                    </div>
                </div>

                <div className="d-flex gap-2">
                    {report.status === 'pending' && (
                        <Button
                            variant="success"
                            onClick={handleGenerateReport}
                            disabled={generating}
                        >
                            {generating ? (
                                <>
                                    <span className="loading-spinner me-2"></span>
                                    Generating...
                                </>
                            ) : (
                                '🚀 Generate Report'
                            )}
                        </Button>
                    )}

                    {report.status === 'completed' && (
                        <>
                            <Button variant="outline-primary" onClick={() => handleExport('pdf')}>
                                📄 Export PDF
                            </Button>
                            <Button variant="outline-primary" onClick={() => handleExport('csv')}>
                                📊 Export CSV
                            </Button>
                            <Button variant="outline-primary" onClick={() => handleExport('json')}>
                                📋 Export JSON
                            </Button>
                        </>
                    )}
                </div>
            </div>

            {error && (
                <Alert variant="danger" className="mb-4">
                    {error}
                </Alert>
            )}

            <Row className="mb-4">
                <Col>
                    <Card>
                        <Card.Body>
                            <h5>Topics Analyzed</h5>
                            <div className="d-flex flex-wrap gap-2 mt-2">
                                {report.topics.map((topic, index) => (
                                    <Badge key={index} bg="primary">
                                        {topic}
                                    </Badge>
                                ))}
                            </div>
                        </Card.Body>
                    </Card>
                </Col>
            </Row>

            {report.status === 'completed' && reportData.length > 0 && (
                <Tabs defaultActiveKey="overview" className="mb-4">
                    <Tab eventKey="overview" title="📊 Overview">
                        <Row>
                            <Col lg={6}>
                                <Card className="mb-4">
                                    <Card.Header>
                                        <h5 className="mb-0">Prediction Scores</h5>
                                    </Card.Header>
                                    <Card.Body>
                                        <div className="chart-container">
                                            {getPredictionScoresChartData() && (
                                                <Bar
                                                    data={getPredictionScoresChartData()!}
                                                    options={{
                                                        responsive: true,
                                                        maintainAspectRatio: false,
                                                        plugins: {
                                                            title: {
                                                                display: true,
                                                                text: 'Topic Prediction Scores (%)'
                                                            },
                                                            legend: {
                                                                display: false
                                                            }
                                                        },
                                                        scales: {
                                                            y: {
                                                                beginAtZero: true,
                                                                max: 100,
                                                                ticks: {
                                                                    callback: (value) => `${value}%`
                                                                }
                                                            }
                                                        }
                                                    }}
                                                />
                                            )}
                                        </div>
                                    </Card.Body>
                                </Card>
                            </Col>

                            <Col lg={6}>
                                <Card className="mb-4">
                                    <Card.Header>
                                        <h5 className="mb-0">Historical Trends</h5>
                                    </Card.Header>
                                    <Card.Body>
                                        <div className="chart-container">
                                            {getHistoricalTrendsChartData() && (
                                                <Line
                                                    data={getHistoricalTrendsChartData()!}
                                                    options={{
                                                        responsive: true,
                                                        maintainAspectRatio: false,
                                                        plugins: {
                                                            title: {
                                                                display: true,
                                                                text: 'Historical Topic Frequency Trends'
                                                            }
                                                        },
                                                        scales: {
                                                            y: {
                                                                beginAtZero: true,
                                                                ticks: {
                                                                    callback: (value) => `${value}%`
                                                                }
                                                            }
                                                        }
                                                    }}
                                                />
                                            )}
                                        </div>
                                    </Card.Body>
                                </Card>
                            </Col>
                        </Row>
                    </Tab>

                    <Tab eventKey="data" title="📋 Detailed Data">
                        <Card>
                            <Card.Body>
                                <Table responsive striped hover>
                                    <thead>
                                        <tr>
                                            <th>Topic</th>
                                            <th>Prediction Score</th>
                                            <th>Confidence</th>
                                            <th>Trend</th>
                                            <th>Quantum Contribution</th>
                                            <th>Classical Contribution</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {reportData.map((item, index) => (
                                            <tr key={index}>
                                                <td>{item.topic}</td>
                                                <td>{(item.prediction_score * 100).toFixed(1)}%</td>
                                                <td>{(item.confidence * 100).toFixed(1)}%</td>
                                                <td>
                                                    <Badge bg={
                                                        item.trend === 'increasing' ? 'success' :
                                                            item.trend === 'decreasing' ? 'danger' : 'warning'
                                                    }>
                                                        {item.trend}
                                                    </Badge>
                                                </td>
                                                <td>{item.quantum_contribution ? `${(item.quantum_contribution * 100).toFixed(1)}%` : 'N/A'}</td>
                                                <td>{item.classical_contribution ? `${(item.classical_contribution * 100).toFixed(1)}%` : 'N/A'}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </Table>
                            </Card.Body>
                        </Card>
                    </Tab>
                </Tabs>
            )}

            {report.status === 'processing' && (
                <Alert variant="info">
                    <div className="d-flex align-items-center">
                        <Spinner animation="border" size="sm" className="me-3" />
                        <div>
                            <strong>Report Generation in Progress</strong>
                            <br />
                            <small>Your quantum-classical analysis is being processed. This may take a few minutes.</small>
                        </div>
                    </div>
                </Alert>
            )}
        </Container>
    );
};

export default ReportDetail;
