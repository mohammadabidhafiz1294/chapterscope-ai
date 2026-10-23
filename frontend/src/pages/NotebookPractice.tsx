import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
    Alert, Badge, Button, Card, Form, Spinner, Table,
} from 'react-bootstrap';
import {
    GenerationApiError, GenerationPayload, NotebookTopic, generateQuestions,
    listTopics, GenerationRequest,
} from '../services/generation';

// Phase 7 practice-question generator. The generator *drafts* questions from
// the notebook's syllabus and past papers; every question is automatically
// validated server-side and either marked VALIDATED or NEEDS_REVIEW (with
// machine-readable reasons). This page never claims a generated answer is
// correct — see the disclaimer below.

const QUESTION_TYPES = [
    { value: '', label: 'Any type' },
    { value: 'multiple_choice', label: 'Multiple choice' },
    { value: 'short_answer', label: 'Short answer' },
    { value: 'numerical', label: 'Numerical' },
    { value: 'true_false', label: 'True / false' },
    { value: 'essay', label: 'Essay' },
];

const DIFFICULTIES = [
    { value: '', label: 'Any difficulty' },
    { value: 'easy', label: 'Easy' },
    { value: 'medium', label: 'Medium' },
    { value: 'hard', label: 'Hard' },
];

const statusVariant = (status: GenerationRequest['status']): string => {
    switch (status) {
        case 'COMPLETED':
            return 'success';
        case 'PARTIAL':
            return 'warning';
        case 'FAILED':
            return 'danger';
        default:
            return 'secondary';
    }
};

const NotebookPractice: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const notebookId = parseInt(id || '0', 10);
    const navigate = useNavigate();

    const [topics, setTopics] = useState<NotebookTopic[]>([]);
    const [loadingTopics, setLoadingTopics] = useState(true);
    const [topicId, setTopicId] = useState<number | ''>('');
    const [count, setCount] = useState(5);
    const [questionType, setQuestionType] = useState('');
    const [difficulty, setDifficulty] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [payload, setPayload] = useState<GenerationPayload | null>(null);

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            try {
                const list = await listTopics(notebookId);
                if (!cancelled) setTopics(list);
            } catch (err) {
                if (!cancelled) {
                    setError(
                        err instanceof GenerationApiError
                            ? err.message
                            : 'Failed to load topics'
                    );
                }
            } finally {
                if (!cancelled) setLoadingTopics(false);
            }
        };
        if (notebookId) load();
        return () => {
            cancelled = true;
        };
    }, [notebookId]);

    const runGenerate = useCallback(async () => {
        if (topicId === '') return;
        setBusy(true);
        setError('');
        try {
            const result = await generateQuestions(notebookId, {
                topic_id: topicId,
                count,
                question_types: questionType ? [questionType] : [],
                difficulty,
            });
            setPayload(result);
        } catch (err) {
            if (err instanceof GenerationApiError) {
                setError(err.message + (err.hint ? ` — ${err.hint}` : ''));
            } else {
                setError('Generation failed');
            }
        } finally {
            setBusy(false);
        }
    }, [notebookId, topicId, count, questionType, difficulty]);

    if (loadingTopics) {
        return (
            <div className="text-center py-5">
                <Spinner animation="border" className="mb-3" />
                <p className="text-muted">Loading topics…</p>
            </div>
        );
    }

    return (
        <div>
            <div className="d-flex justify-content-between align-items-center mb-3">
                <h4 className="mb-0">Practice generator</h4>
                <Link to={`/notebooks/${notebookId}`}>
                    <Button variant="outline-secondary" size="sm">
                        ← Back to notebook
                    </Button>
                </Link>
            </div>

            <Alert variant="info">
                Questions are drafted by a language model from this notebook's
                syllabus and past papers, then validated automatically.
                <strong>
                    {' '}This is not an exam prediction, and a generated answer
                    is not guaranteed to be correct.
                </strong>{' '}
                Questions that fail a check are kept and flagged
                <em> needs review</em> rather than shown as verified.
            </Alert>

            {error && <Alert variant="danger">{error}</Alert>}

            <Card className="mb-4">
                <Card.Body>
                    <Form>
                        <Form.Group className="mb-3">
                            <Form.Label>Topic</Form.Label>
                            <Form.Select
                                value={topicId}
                                onChange={(e) =>
                                    setTopicId(
                                        e.target.value
                                            ? parseInt(e.target.value, 10)
                                            : ''
                                    )
                                }
                            >
                                <option value="">Choose a topic…</option>
                                {topics.map((topic) => (
                                    <option key={topic.id} value={topic.id}>
                                        {topic.name}
                                    </option>
                                ))}
                            </Form.Select>
                            {topics.length === 0 && (
                                <Form.Text className="text-muted">
                                    This notebook has no topics yet. Confirm or
                                    create topics in Analytics first.
                                </Form.Text>
                            )}
                        </Form.Group>

                        <div className="d-flex gap-3 mb-3">
                            <Form.Group className="flex-fill">
                                <Form.Label>Questions</Form.Label>
                                <Form.Control
                                    type="number"
                                    min={1}
                                    max={20}
                                    value={count}
                                    onChange={(e) =>
                                        setCount(parseInt(e.target.value, 10) || 1)
                                    }
                                />
                            </Form.Group>
                            <Form.Group className="flex-fill">
                                <Form.Label>Type</Form.Label>
                                <Form.Select
                                    value={questionType}
                                    onChange={(e) => setQuestionType(e.target.value)}
                                >
                                    {QUESTION_TYPES.map((t) => (
                                        <option key={t.value} value={t.value}>
                                            {t.label}
                                        </option>
                                    ))}
                                </Form.Select>
                            </Form.Group>
                            <Form.Group className="flex-fill">
                                <Form.Label>Difficulty</Form.Label>
                                <Form.Select
                                    value={difficulty}
                                    onChange={(e) => setDifficulty(e.target.value)}
                                >
                                    {DIFFICULTIES.map((d) => (
                                        <option key={d.value} value={d.value}>
                                            {d.label}
                                        </option>
                                    ))}
                                </Form.Select>
                            </Form.Group>
                        </div>

                        <Button
                            variant="primary"
                            onClick={runGenerate}
                            disabled={busy || topicId === ''}
                        >
                            {busy ? (
                                <>
                                    <Spinner
                                        as="span"
                                        animation="border"
                                        size="sm"
                                        className="me-2"
                                    />
                                    Generating…
                                </>
                            ) : (
                                'Generate practice questions'
                            )}
                        </Button>
                    </Form>
                </Card.Body>
            </Card>

            {payload && (
                <Card>
                    <Card.Header className="d-flex justify-content-between align-items-center">
                        <Card.Title as="h5" className="mb-0">
                            Generated paper
                        </Card.Title>
                        <div>
                            <Badge bg={statusVariant(payload.request.status)}>
                                {payload.request.status === 'FAILED'
                                    ? 'failed_validation'
                                    : payload.request.status}
                            </Badge>{' '}
                            <Badge bg="secondary">
                                {payload.request.questions_validated} validated
                            </Badge>{' '}
                            <Badge bg="warning" text="dark">
                                {payload.request.questions_needs_review} to review
                            </Badge>
                        </div>
                    </Card.Header>
                    {payload.questions.length === 0 ? (
                        <Card.Body className="text-muted">
                            No questions were generated for this topic.
                        </Card.Body>
                    ) : (
                        <Table hover className="mb-0 align-middle">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Prompt</th>
                                    <th>Type</th>
                                    <th>Marks</th>
                                    <th>Validation</th>
                                    <th />
                                </tr>
                            </thead>
                            <tbody>
                                {payload.questions.map((q, index) => (
                                    <tr key={q.id}>
                                        <td>{index + 1}</td>
                                        <td style={{ maxWidth: 360 }}>
                                            {q.question_text}
                                        </td>
                                        <td>{q.question_type || '—'}</td>
                                        <td>{q.marks ?? '—'}</td>
                                        <td>
                                            <Badge
                                                bg={
                                                    q.validation_status === 'VALIDATED'
                                                        ? 'success'
                                                        : 'warning'
                                                }
                                                text={
                                                    q.validation_status === 'VALIDATED'
                                                        ? undefined
                                                        : 'dark'
                                                }
                                            >
                                                {q.validation_status === 'VALIDATED'
                                                    ? 'verified'
                                                    : 'needs_review'}
                                            </Badge>
                                        </td>
                                        <td>
                                            <Button
                                                size="sm"
                                                variant="outline-primary"
                                                onClick={() =>
                                                    navigate(
                                                        `/notebooks/${notebookId}/generated/${q.id}`
                                                    )
                                                }
                                            >
                                                Open
                                            </Button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </Table>
                    )}
                </Card>
            )}
        </div>
    );
};

export default NotebookPractice;
