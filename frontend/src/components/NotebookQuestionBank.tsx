import React, { useEffect, useState } from 'react';
import { Alert, Card, Form, Spinner, Table } from 'react-bootstrap';
import { listQuestions } from '../services/notebooks';

interface Props { notebookId: number; }
type Question = Awaited<ReturnType<typeof listQuestions>>['results'][number];

const NotebookQuestionBank: React.FC<Props> = ({ notebookId }) => {
    const [questions, setQuestions] = useState<Question[]>([]);
    const [filters, setFilters] = useState({ year: '', topic: '', question_type: '', difficulty: '', marks: '' });
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    useEffect(() => {
        let active = true;
        setLoading(true);
        listQuestions(notebookId, Object.fromEntries(Object.entries(filters).filter(([, value]) => value)))
            .then((response) => { if (active) setQuestions(response.results); })
            .catch(() => { if (active) setError('Question Bank is unavailable. Check your connection or permissions.'); })
            .finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, [notebookId, filters]);
    const update = (key: keyof typeof filters, value: string) => setFilters((current) => ({ ...current, [key]: value }));
    return <div>
        {error && <Alert variant="danger">{error}</Alert>}
        <Card className="mb-3"><Card.Body><div className="row g-2">
            <Form.Group className="col-sm-2"><Form.Label>Year</Form.Label><Form.Control aria-label="Filter by year" value={filters.year} onChange={(e) => update('year', e.target.value)} /></Form.Group>
            <Form.Group className="col-sm-2"><Form.Label>Topic ID</Form.Label><Form.Control aria-label="Filter by topic" value={filters.topic} onChange={(e) => update('topic', e.target.value)} /></Form.Group>
            <Form.Group className="col-sm-3"><Form.Label>Type</Form.Label><Form.Select value={filters.question_type} onChange={(e) => update('question_type', e.target.value)}><option value="">All types</option><option value="multiple_choice">Multiple choice</option><option value="short_answer">Short answer</option><option value="numerical">Numerical</option><option value="essay">Essay</option></Form.Select></Form.Group>
            <Form.Group className="col-sm-3"><Form.Label>Difficulty</Form.Label><Form.Select value={filters.difficulty} onChange={(e) => update('difficulty', e.target.value)}><option value="">All difficulties</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></Form.Select></Form.Group>
            <Form.Group className="col-sm-2"><Form.Label>Marks</Form.Label><Form.Control type="number" min="0" aria-label="Filter by marks" value={filters.marks} onChange={(e) => update('marks', e.target.value)} /></Form.Group>
        </div></Card.Body></Card>
        {loading ? <div className="text-center py-5"><Spinner animation="border" /></div> : questions.length === 0 ? <Card body className="text-muted">No questions match these filters.</Card> :
            <Card><Table responsive hover className="mb-0"><thead><tr><th>Question</th><th>Source</th><th>Year</th><th>Marks</th><th>Type</th><th>Difficulty</th><th>Page</th></tr></thead><tbody>{questions.map((q) => <tr key={q.id}><td>{q.question_number}: {q.raw_text}</td><td>{q.exam_paper_title}</td><td>{q.year}</td><td>{q.marks ?? '—'}</td><td>{q.question_type || 'Unclassified'}</td><td>{q.difficulty || '—'}</td><td>{q.source_page_number ?? q.page_reference ?? '—'}</td></tr>)}</tbody></Table></Card>}
    </div>;
};
export default NotebookQuestionBank;
