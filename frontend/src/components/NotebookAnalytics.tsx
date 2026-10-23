import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    Alert, Badge, Button, Card, Col, Row, Spinner, Table,
} from 'react-bootstrap';
import {
    BarElement, CategoryScale, Chart as ChartJS, Legend, LinearScale,
    LineElement, PointElement, Title, Tooltip,
} from 'chart.js';
import { Bar, Line } from 'react-chartjs-2';
import {
    AnalyticsReport, ProposalsResult, ReviewQueue, Weighting,
    apiErrorMessage, getAnalytics, getReviewQueue, runProposals, submitReview,
} from '../services/analytics';

ChartJS.register(
    CategoryScale, LinearScale, PointElement, LineElement, BarElement,
    Tooltip, Legend, Title,
);

interface Props {
    notebookId: number;
    archived: boolean;
}

const formatNumber = (value: number, digits = 3): string =>
    Number.isFinite(value) ? value.toFixed(digits) : '—';

const typeLabel = (value: string): string =>
    value ? value.replace(/_/g, ' ') : 'unspecified';

const textOf = (entry: ProposalsResult): string[] => {
    const lines = [
        `Proposed ${entry.links_created.length} link(s) and ` +
        `${entry.topics_created.length} new topic label(s) for review.`,
    ];
    if (entry.low_confidence.length > 0) {
        lines.push(
            `${entry.low_confidence.length} suggestion(s) scored below the ` +
            `confidence threshold and were not applied.`,
        );
    }
    if (entry.unresolved.length > 0) {
        lines.push(
            `${entry.unresolved.length} label(s) matched several topics and ` +
            `need a human choice.`,
        );
    }
    if (entry.notices.includes('nothing_applied')) {
        lines.push('Nothing new was created (everything already exists).');
    }
    return lines;
};

const NotebookAnalytics: React.FC<Props> = ({ notebookId, archived }) => {
    const [report, setReport] = useState<AnalyticsReport | null>(null);
    const [queue, setQueue] = useState<ReviewQueue | null>(null);
    const [weighting, setWeighting] = useState<Weighting>('primary');
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [infoLines, setInfoLines] = useState<string[]>([]);

    const load = useCallback(async () => {
        try {
            const [analytics, pending] = await Promise.all([
                getAnalytics(notebookId, { weighting }),
                getReviewQueue(notebookId),
            ]);
            setReport(analytics);
            setQueue(pending);
            setError('');
        } catch (err) {
            setError(apiErrorMessage(err));
        } finally {
            setLoading(false);
        }
    }, [notebookId, weighting]);

    useEffect(() => {
        setLoading(true);
        load();
    }, [load]);

    const runBusy = async (fn: () => Promise<void>) => {
        setBusy(true);
        setError('');
        try {
            await fn();
        } catch (err) {
            setError(apiErrorMessage(err));
        } finally {
            setBusy(false);
        }
    };

    const propose = (useLlm: boolean) => runBusy(async () => {
        const result = await runProposals(notebookId, { use_llm: useLlm });
        setInfoLines(textOf(result));
        await load();
    });

    const review = (
        body: Parameters<typeof submitReview>[1],
    ) => runBusy(async () => {
        await submitReview(notebookId, body);
        setInfoLines([]);
        await load();
    });

    const lineData = useMemo(() => {
        if (!report) return null;
        const topics = report.topics.slice(0, 5);
        return {
            labels: report.years.map((row) => String(row.year)),
            datasets: topics.map((topic) => ({
                label: topic.name,
                data: report.years.map(
                    (row) => row.topic_prevalence[String(topic.id)] ?? 0,
                ),
                tension: 0.25,
            })),
        };
    }, [report]);

    const marksData = useMemo(() => {
        if (!report) return null;
        return {
            labels: report.topics.map((topic) => topic.name),
            datasets: [
                {
                    label: 'Normalized marks share',
                    data: report.topics.map((topic) => topic.marks_share),
                    backgroundColor: 'rgba(13, 110, 253, 0.6)',
                },
            ],
        };
    }, [report]);

    if (loading) {
        return (
            <div className="text-center py-5">
                <Spinner animation="border" className="mb-2" />
                <p className="text-muted mb-0">Loading analytics…</p>
            </div>
        );
    }

    if (!report) {
        return (
            <Alert variant="danger">
                {error || 'Analytics could not be loaded.'}
            </Alert>
        );
    }

    const coverage = report.coverage;
    const pendingLinks = queue?.links ?? [];
    const pendingTopics = queue?.topics ?? [];
    const pendingTypes = queue?.types ?? [];

    return (
        <div>
            {error && <Alert variant="danger">{error}</Alert>}
            {infoLines.map((line) => (
                <Alert variant="info" key={line}>{line}</Alert>
            ))}
            {report.notices.length > 0 && (
                <Alert variant="warning">
                    <Alert.Heading as="h6">Data notices</Alert.Heading>
                    <ul className="mb-0">
                        {report.notices.map((code) => (
                            <li key={code}>
                                {report.notice_labels[code] ?? code}
                            </li>
                        ))}
                    </ul>
                </Alert>
            )}

            <div className="d-flex flex-wrap justify-content-between align-items-center mb-3 gap-2">
                <div>
                    {(['primary', 'weighted'] as Weighting[]).map((mode) => (
                        <Button
                            key={mode}
                            size="sm"
                            variant={
                                weighting === mode ? 'primary' : 'outline-primary'
                            }
                            className="me-2"
                            onClick={() => setWeighting(mode)}
                        >
                            {mode === 'primary' ? 'Primary counts' : 'Weighted counts'}
                        </Button>
                    ))}
                    <span className="text-muted small">
                        Definitions v{report.definitions_version} · generated{' '}
                        {new Date(report.generated_at).toLocaleString()}
                    </span>
                </div>
                <div>
                    <Button
                        size="sm"
                        variant="outline-success"
                        className="me-2"
                        disabled={busy || archived}
                        onClick={() => propose(false)}
                    >
                        Propose labels (keyword pass)
                    </Button>
                    <Button
                        size="sm"
                        variant="outline-secondary"
                        disabled={busy || archived}
                        title="Requires GEMINI_API_KEY on the server"
                        onClick={() => propose(true)}
                    >
                        Propose labels (LLM)
                    </Button>
                </div>
            </div>

            <Row className="mb-3">
                <Col md={3} sm={6}>
                    <Card className="text-center h-100">
                        <Card.Body>
                            <h4>
                                {coverage.papers_with_questions}/
                                {coverage.papers_total}
                            </h4>
                            <p className="text-muted mb-0">Papers with questions</p>
                        </Card.Body>
                    </Card>
                </Col>
                <Col md={3} sm={6}>
                    <Card className="text-center h-100">
                        <Card.Body>
                            <h4>
                                {coverage.questions_classified}/
                                {coverage.questions_total}
                            </h4>
                            <p className="text-muted mb-0">Questions classified</p>
                        </Card.Body>
                    </Card>
                </Col>
                <Col md={3} sm={6}>
                    <Card className="text-center h-100">
                        <Card.Body>
                            <h4>{coverage.links_pending_review}</h4>
                            <p className="text-muted mb-0">Links awaiting review</p>
                        </Card.Body>
                    </Card>
                </Col>
                <Col md={3} sm={6}>
                    <Card className="text-center h-100">
                        <Card.Body>
                            <h4>{coverage.topics_total}</h4>
                            <p className="text-muted mb-0">
                                Topics ({coverage.topics_needs_review} unreviewed)
                            </p>
                        </Card.Body>
                    </Card>
                </Col>
            </Row>

            <Row className="mb-3">
                <Col lg={6}>
                    <Card className="h-100">
                        <Card.Header>Paper prevalence per year</Card.Header>
                        <Card.Body>
                            {lineData && report.years.length > 0 ? (
                                <Line
                                    data={lineData}
                                    options={{
                                        responsive: true,
                                        plugins: {
                                            legend: { position: 'bottom' },
                                        },
                                        scales: {
                                            y: {
                                                min: 0,
                                                max: 1,
                                                title: {
                                                    display: true,
                                                    text: 'Share of papers',
                                                },
                                            },
                                        },
                                    }}
                                />
                            ) : (
                                <p className="text-muted mb-0">
                                    Not enough data for a yearly series yet.
                                </p>
                            )}
                        </Card.Body>
                    </Card>
                </Col>
                <Col lg={6}>
                    <Card className="h-100">
                        <Card.Header>Normalized marks share</Card.Header>
                        <Card.Body>
                            {marksData && report.topics.length > 0 ? (
                                <Bar
                                    data={marksData}
                                    options={{
                                        responsive: true,
                                        plugins: {
                                            legend: { display: false },
                                        },
                                        scales: {
                                            y: {
                                                beginAtZero: true,
                                                title: {
                                                    display: true,
                                                    text: 'Sum of marks / paper totals',
                                                },
                                            },
                                        },
                                    }}
                                />
                            ) : (
                                <p className="text-muted mb-0">
                                    No classified questions to show marks for.
                                </p>
                            )}
                        </Card.Body>
                    </Card>
                </Col>
            </Row>

            <Card className="mb-3">
                <Card.Header>Topic ranking</Card.Header>
                <Card.Body>
                    <Table hover size="sm" className="align-middle">
                        <thead>
                            <tr>
                                <th>Topic</th>
                                <th>Score</th>
                                <th>Paper prevalence</th>
                                <th>Question share</th>
                                <th>Marks share</th>
                                <th>Trend (slope)</th>
                                <th>Syllabus</th>
                            </tr>
                        </thead>
                        <tbody>
                            {report.topics.map((topic) => (
                                <tr key={topic.id}>
                                    <td>
                                        {topic.name}{' '}
                                        {topic.aliases.map((alias) => (
                                            <Badge
                                                bg="light"
                                                text="dark"
                                                key={alias}
                                                className="me-1"
                                            >
                                                {alias}
                                            </Badge>
                                        ))}
                                    </td>
                                    <td><strong>{formatNumber(topic.score, 2)}</strong></td>
                                    <td>{formatNumber(topic.paper_prevalence)}</td>
                                    <td>{formatNumber(topic.question_share)}</td>
                                    <td>{formatNumber(topic.marks_share)}</td>
                                    <td>
                                        {topic.trend_slope === null
                                            ? '—'
                                            : `${topic.trend_slope > 0 ? '+' : ''}${formatNumber(topic.trend_slope, 2)}`}
                                    </td>
                                    <td>{formatNumber(topic.syllabus_importance, 2)}</td>
                                </tr>
                            ))}
                            {report.topics.length === 0 && (
                                <tr>
                                    <td colSpan={7} className="text-muted">
                                        No classified questions yet — propose and
                                        review labels to populate the ranking.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </Table>
                    {report.topics_truncated && (
                        <p className="text-muted small mb-2">
                            Only the highest-scoring topics are shown; ask for
                            more with the <code>topics</code> parameter.
                        </p>
                    )}
                    <div className="small text-muted">
                        {Object.entries(report.measure_labels).map(([key, label]) => (
                            <div key={key}><em>{key}</em>: {label}</div>
                        ))}
                        {Object.entries(report.ranking.component_labels).map(
                            ([key, label]) => (
                                <div key={key}><em>{key}</em>: {label}</div>
                            ),
                        )}
                    </div>
                    <Alert variant="secondary" className="mt-2 mb-0 small">
                        {report.ranking.disclaimer}
                    </Alert>
                </Card.Body>
            </Card>

            <Row className="mb-3">
                <Col md={6}>
                    <Card className="h-100">
                        <Card.Header>Question types</Card.Header>
                        <Card.Body>
                            {report.question_types.length === 0 ? (
                                <p className="text-muted mb-0">No questions yet.</p>
                            ) : (
                                <Table size="sm" className="mb-0">
                                    <thead>
                                        <tr>
                                            <th>Type</th>
                                            <th className="text-end">Questions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {report.question_types.map((row) => (
                                            <tr key={row.type}>
                                                <td>{typeLabel(row.type)}</td>
                                                <td className="text-end">{row.count}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </Table>
                            )}
                        </Card.Body>
                    </Card>
                </Col>
                <Col md={6}>
                    <Card className="h-100">
                        <Card.Header>Review queue</Card.Header>
                        <Card.Body>
                            {archived && (
                                <Alert variant="warning" className="py-2">
                                    This notebook is archived (read-only).
                                </Alert>
                            )}
                            {pendingLinks.length + pendingTopics.length +
                                pendingTypes.length === 0 ? (
                                <p className="text-muted mb-0">
                                    Nothing is waiting for review. Run a proposal
                                    pass to suggest topic and type labels.
                                </p>
                            ) : (
                                <div className="small">
                                    {pendingLinks.map((link) => (
                                        <div
                                            className="border rounded p-2 mb-2"
                                            key={`link-${link.id}`}
                                        >
                                            <div className="d-flex justify-content-between">
                                                <span>
                                                    <Badge bg="primary" className="me-1">
                                                        {link.role}
                                                    </Badge>
                                                    <strong>{link.topic_name}</strong>
                                                    <span className="text-muted ms-1">
                                                        Q{link.question_number} ·{' '}
                                                        {link.classification_source}
                                                        {link.confidence !== null &&
                                                            ` · ${formatNumber(link.confidence, 2)}`}
                                                    </span>
                                                </span>
                                                <span>
                                                    <Button
                                                        size="sm"
                                                        variant="outline-success"
                                                        className="me-1"
                                                        disabled={busy || archived}
                                                        onClick={() => review({
                                                            links: [
                                                                { id: link.id, action: 'confirm' },
                                                            ],
                                                        })}
                                                    >
                                                        Confirm
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="outline-danger"
                                                        disabled={busy || archived}
                                                        onClick={() => review({
                                                            links: [
                                                                { id: link.id, action: 'reject' },
                                                            ],
                                                        })}
                                                    >
                                                        Reject
                                                    </Button>
                                                </span>
                                            </div>
                                            <div className="text-truncate text-muted">
                                                {link.text}
                                            </div>
                                        </div>
                                    ))}
                                    {pendingTopics.map((topic) => (
                                        <div
                                            className="border rounded p-2 mb-2"
                                            key={`topic-${topic.id}`}
                                        >
                                            <div className="d-flex justify-content-between">
                                                <span>
                                                    <strong>{topic.name}</strong>
                                                    <span className="text-muted ms-1">
                                                        proposed topic
                                                    </span>
                                                </span>
                                                <span>
                                                    <Button
                                                        size="sm"
                                                        variant="outline-success"
                                                        className="me-1"
                                                        disabled={busy || archived}
                                                        onClick={() => review({
                                                            topics: [
                                                                { id: topic.id, action: 'confirm' },
                                                            ],
                                                        })}
                                                    >
                                                        Confirm
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="outline-danger"
                                                        disabled={busy || archived}
                                                        onClick={() => review({
                                                            topics: [
                                                                { id: topic.id, action: 'reject' },
                                                            ],
                                                        })}
                                                    >
                                                        Reject
                                                    </Button>
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                    {pendingTypes.map((pending) => (
                                        <div
                                            className="border rounded p-2 mb-2"
                                            key={`type-${pending.question_id}`}
                                        >
                                            <div className="d-flex justify-content-between">
                                                <span>
                                                    <strong>{typeLabel(pending.question_type)}</strong>
                                                    <span className="text-muted ms-1">
                                                        Q{pending.question_number} ·{' '}
                                                        {pending.type_source}
                                                        {pending.type_confidence !== null &&
                                                            ` · ${formatNumber(pending.type_confidence, 2)}`}
                                                    </span>
                                                </span>
                                                <span>
                                                    <Button
                                                        size="sm"
                                                        variant="outline-success"
                                                        className="me-1"
                                                        disabled={busy || archived}
                                                        onClick={() => review({
                                                            types: [
                                                                {
                                                                    question_id: pending.question_id,
                                                                    action: 'confirm',
                                                                },
                                                            ],
                                                        })}
                                                    >
                                                        Confirm
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="outline-danger"
                                                        disabled={busy || archived}
                                                        onClick={() => review({
                                                            types: [
                                                                {
                                                                    question_id: pending.question_id,
                                                                    action: 'reject',
                                                                },
                                                            ],
                                                        })}
                                                    >
                                                        Reject
                                                    </Button>
                                                </span>
                                            </div>
                                            <div className="text-truncate text-muted">
                                                {pending.text}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </Card.Body>
                    </Card>
                </Col>
            </Row>
        </div>
    );
};

export default NotebookAnalytics;
