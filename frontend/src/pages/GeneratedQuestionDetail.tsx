import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
    Alert, Badge, Button, Card, Spinner,
} from 'react-bootstrap';
import {
    GenerationApiError, GeneratedQuestion, getGeneratedQuestion,
} from '../services/generation';

// Reopen one generated practice question. This is a *study* artifact drafted
// by a model and validated automatically: a VALIDATED badge means it passed
// every automatic check, not that a human confirmed the answer is correct.

const QuestionDetail: React.FC = () => {
    const { id, qid } = useParams<{ id: string; qid: string }>();
    const notebookId = parseInt(id || '0', 10);
    const questionId = parseInt(qid || '0', 10);

    const [question, setQuestion] = useState<GeneratedQuestion | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [showAnswer, setShowAnswer] = useState(false);

    const load = useCallback(async () => {
        try {
            const data = await getGeneratedQuestion(notebookId, questionId);
            setQuestion(data);
        } catch (err) {
            setError(
                err instanceof GenerationApiError
                    ? err.message
                    : 'Failed to load question'
            );
        } finally {
            setLoading(false);
        }
    }, [notebookId, questionId]);

    useEffect(() => {
        load();
    }, [load]);

    if (loading) {
        return (
            <div className="text-center py-5">
                <Spinner animation="border" className="mb-3" />
                <p className="text-muted">Loading question…</p>
            </div>
        );
    }

    if (!question) {
        return (
            <Alert variant="danger">
                {error || 'Question not found'}
                <div className="mt-2">
                    <Link to={`/notebooks/${notebookId}/practice`}>
                        <Button size="sm" variant="outline-secondary">
                            ← Back to practice
                        </Button>
                    </Link>
                </div>
            </Alert>
        );
    }

    return (
        <div>
            <div className="d-flex justify-content-between align-items-center mb-3">
                <h4 className="mb-0">Generated question</h4>
                <Link to={`/notebooks/${notebookId}/practice`}>
                    <Button variant="outline-secondary" size="sm">
                        ← Back to practice
                    </Button>
                </Link>
            </div>

            {question.validation_status === 'NEEDS_REVIEW' && (
                <Alert variant="warning">
                    This question failed one or more automatic checks and is
                    flagged <strong>needs review</strong>. Treat it as a draft,
                    not a verified question.
                    {question.validation_report.length > 0 && (
                        <ul className="mb-0 mt-2">
                            {question.validation_report.map((reason) => (
                                <li key={reason}>{reason}</li>
                            ))}
                        </ul>
                    )}
                </Alert>
            )}

            <Card className="mb-3">
                <Card.Header className="d-flex justify-content-between align-items-center">
                    <Card.Title as="h5" className="mb-0">
                        Question
                    </Card.Title>
                    <div>
                        <Badge
                            bg={
                                question.validation_status === 'VALIDATED'
                                    ? 'success'
                                    : 'warning'
                            }
                            text={
                                question.validation_status === 'VALIDATED'
                                    ? undefined
                                    : 'dark'
                            }
                        >
                            {question.validation_status === 'VALIDATED'
                                ? 'Validated'
                                : 'Needs review'}
                        </Badge>{' '}
                        <Badge bg="secondary">{question.question_type || 'unspecified'}</Badge>{' '}
                        {question.marks != null && (
                            <Badge bg="secondary">{question.marks} marks</Badge>
                        )}{' '}
                        {question.difficulty && (
                            <Badge bg="secondary">{question.difficulty}</Badge>
                        )}
                    </div>
                </Card.Header>
                <Card.Body>
                    <p style={{ whiteSpace: 'pre-wrap' }}>{question.question_text}</p>

                    {question.options.length > 0 && (
                        <ul className="mt-3">
                            {question.options.map((option, index) => (
                                <li key={index}>{option}</li>
                            ))}
                        </ul>
                    )}
                </Card.Body>
            </Card>

            <Card className="mb-3">
                <Card.Header className="d-flex justify-content-between align-items-center">
                    <Card.Title as="h5" className="mb-0">
                        Answer
                    </Card.Title>
                    <Button
                        size="sm"
                        variant="outline-primary"
                        onClick={() => setShowAnswer((v) => !v)}
                    >
                        {showAnswer ? 'Hide' : 'Show'} answer
                    </Button>
                </Card.Header>
                {showAnswer && (
                    <Card.Body>
                        {question.answer_text ? (
                            <p style={{ whiteSpace: 'pre-wrap' }}>
                                {question.answer_text}
                            </p>
                        ) : (
                            <p className="text-muted mb-0">
                                No answer was generated for this question.
                            </p>
                        )}
                        {question.solution_text && (
                            <>
                                <h6 className="mt-3">Solution</h6>
                                <p
                                    className="mb-0"
                                    style={{ whiteSpace: 'pre-wrap' }}
                                >
                                    {question.solution_text}
                                </p>
                            </>
                        )}
                        {question.marking_rubric.length > 0 && (
                            <>
                                <h6 className="mt-3">Marking rubric</h6>
                                <ul className="mb-0">
                                    {question.marking_rubric.map((item, index) => (
                                        <li key={index}>
                                            {item.criterion} — {item.marks} marks
                                        </li>
                                    ))}
                                </ul>
                            </>
                        )}
                        {question.answer_confidence != null && (
                            <p className="text-muted mt-3 mb-0">
                                Model confidence:{' '}
                                {(question.answer_confidence * 100).toFixed(0)}%
                            </p>
                        )}
                    </Card.Body>
                )}
            </Card>

            <Card>
                <Card.Header>
                    <Card.Title as="h5" className="mb-0">
                        Sources
                    </Card.Title>
                </Card.Header>
                {question.source_refs.length === 0 ? (
                    <Card.Body className="text-muted">
                        No valid sources were cited for this question.
                    </Card.Body>
                ) : (
                    <ul className="list-group list-group-flush">
                        {question.source_refs.map((ref) => (
                            <li key={ref.source_key} className="list-group-item">
                                <Badge bg="secondary" className="me-2">
                                    {ref.source_type}
                                </Badge>
                                {ref.document_title && (
                                    <span className="me-2">{ref.document_title}</span>
                                )}
                                {ref.question_number && (
                                    <span className="me-2">
                                        Q{ref.question_number}
                                    </span>
                                )}
                                {ref.year && (
                                    <span className="me-2">{ref.year}</span>
                                )}
                                {ref.page_number != null && (
                                    <span className="text-muted">
                                        p.{ref.page_number}
                                    </span>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
        </div>
    );
};

export default QuestionDetail;
