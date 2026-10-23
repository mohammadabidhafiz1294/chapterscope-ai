import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
    Container, Card, Button, Badge, Table, Alert, Spinner, Row, Col, Nav,
} from 'react-bootstrap';
import {
    CourseNotebook, getNotebook, archiveNotebook, unarchiveNotebook,
    deleteNotebook, listPapers,
} from '../services/notebooks';
import NotebookAnalytics from '../components/NotebookAnalytics';
import NotebookChat from '../components/NotebookChat';
import NotebookSources from '../components/NotebookSources';
import NotebookQuestionBank from '../components/NotebookQuestionBank';

const NotebookDetail: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [notebook, setNotebook] = useState<CourseNotebook | null>(null);
    const [papers, setPapers] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [tab, setTab] = useState<'overview' | 'sources' | 'questions' | 'analytics' | 'chat'>('overview');

    useEffect(() => {
        if (!id) return;
        const nbId = parseInt(id, 10);
        load(nbId);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    const load = async (nbId: number) => {
        try {
            setLoading(true);
            const [nb, paperList] = await Promise.all([
                getNotebook(nbId),
                listPapers(nbId),
            ]);
            setNotebook(nb);
            setPapers(paperList.results);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load notebook');
        } finally {
            setLoading(false);
        }
    };

    const handleArchiveToggle = async () => {
        if (!notebook) return;
        try {
            const updated = notebook.is_archived
                ? await unarchiveNotebook(notebook.id)
                : await archiveNotebook(notebook.id);
            setNotebook(updated);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Archive failed');
        }
    };

    const handleDelete = async () => {
        if (!notebook) return;
        if (
            !window.confirm(
                `Delete notebook "${notebook.title}"? This cannot be undone.`
            )
        ) {
            return;
        }
        try {
            await deleteNotebook(notebook.id);
            navigate('/notebooks');
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : 'Delete failed — detach syllabus/papers first.'
            );
        }
    };

    if (loading) {
        return (
            <Container className="d-flex justify-content-center align-items-center" style={{ minHeight: '50vh' }}>
                <div className="text-center">
                    <Spinner animation="border" className="mb-3" />
                    <p>Loading notebook...</p>
                </div>
            </Container>
        );
    }

    if (!notebook) {
        return (
            <Container>
                <Alert variant="danger">{error || 'Notebook not found'}</Alert>
                <Link to="/notebooks">
                    <Button variant="outline-secondary">← Back to notebooks</Button>
                </Link>
            </Container>
        );
    }

    return (
        <Container>
            <div className="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <Link to="/notebooks" className="text-decoration-none">
                        ← Notebooks
                    </Link>
                    <h1 className="mt-2 mb-1">
                        {notebook.title}{' '}
                        <Badge bg={notebook.is_archived ? 'secondary' : 'success'}>
                            {notebook.is_archived ? 'Archived' : 'Active'}
                        </Badge>
                    </h1>
                    <p className="text-muted mb-0">
                        {notebook.course_code && <span>{notebook.course_code} · </span>}
                        {notebook.institution}
                    </p>
                </div>
                <div className="d-flex gap-2">
                    <Button
                        variant="outline-info"
                        onClick={() => setTab('chat')}
                    >
                        Chat
                    </Button>
                    <Button
                        variant="outline-success"
                        onClick={() => navigate(`/notebooks/${notebook.id}/practice`)}
                    >
                        Practice
                    </Button>
                    <Button
                        variant={notebook.is_archived ? 'outline-success' : 'outline-secondary'}
                        onClick={handleArchiveToggle}
                    >
                        {notebook.is_archived ? 'Unarchive' : 'Archive'}
                    </Button>
                    <Button variant="outline-danger" onClick={handleDelete}>
                        Delete
                    </Button>
                </div>
            </div>

            {error && <Alert variant="danger">{error}</Alert>}

            <Nav variant="tabs" className="mb-4">
                <Nav.Item>
                    <Nav.Link
                        active={tab === 'overview'}
                        onClick={() => setTab('overview')}
                    >
                        Overview
                    </Nav.Link>
                </Nav.Item>
                <Nav.Item>
                    <Nav.Link active={tab === 'sources'} onClick={() => setTab('sources')}>Sources</Nav.Link>
                </Nav.Item>
                <Nav.Item>
                    <Nav.Link active={tab === 'questions'} onClick={() => setTab('questions')}>Question Bank</Nav.Link>
                </Nav.Item>
                <Nav.Item>
                    <Nav.Link
                        active={tab === 'analytics'}
                        onClick={() => setTab('analytics')}
                    >
                        Analytics
                    </Nav.Link>
                </Nav.Item>
                <Nav.Item>
                    <Nav.Link active={tab === 'chat'} onClick={() => setTab('chat')}>Chat</Nav.Link>
                </Nav.Item>
                <Nav.Item>
                    <Nav.Link as={Link} to={`/notebooks/${notebook.id}/practice`}>Generate Questions</Nav.Link>
                </Nav.Item>
            </Nav>

            {tab === 'sources' ? (
                <NotebookSources notebookId={notebook.id} archived={notebook.is_archived} />
            ) : tab === 'questions' ? (
                <NotebookQuestionBank notebookId={notebook.id} />
            ) : tab === 'analytics' ? (
                <NotebookAnalytics
                    notebookId={notebook.id}
                    archived={notebook.is_archived}
                />
            ) : tab === 'chat' ? (
                <NotebookChat
                    notebookId={notebook.id}
                    archived={notebook.is_archived}
                />
            ) : (
                <>
            <Row className="mb-4">
                <Col md={4}>
                    <Card className="text-center">
                        <Card.Body>
                            <h3>{notebook.syllabus_count}</h3>
                            <p className="text-muted mb-0">Syllabus documents</p>
                        </Card.Body>
                    </Card>
                </Col>
                <Col md={4}>
                    <Card className="text-center">
                        <Card.Body>
                            <h3>{notebook.paper_count}</h3>
                            <p className="text-muted mb-0">Exam papers</p>
                        </Card.Body>
                    </Card>
                </Col>
                <Col md={4}>
                    <Card className="text-center">
                        <Card.Body>
                            <h3>{notebook.question_count}</h3>
                            <p className="text-muted mb-0">Questions</p>
                        </Card.Body>
                    </Card>
                </Col>
            </Row>

            {notebook.description && (
                <Card className="mb-4">
                    <Card.Body>
                        <Card.Title>Description</Card.Title>
                        <p className="mb-0">{notebook.description}</p>
                    </Card.Body>
                </Card>
            )}

            <Card>
                <Card.Header>
                    <Card.Title as="h5" className="mb-0">Attached exam papers</Card.Title>
                </Card.Header>
                {papers.length === 0 ? (
                    <Card.Body className="text-muted">
                        No papers attached yet. Upload a paper and assign it to this
                        notebook, or attach an existing one.
                    </Card.Body>
                ) : (
                    <Table hover className="mb-0 align-middle">
                        <thead>
                            <tr>
                                <th>Title</th>
                                <th>Year</th>
                                <th>Processed</th>
                            </tr>
                        </thead>
                        <tbody>
                            {papers.map((p) => (
                                <tr key={p.id}>
                                    <td>{p.title}</td>
                                    <td>{p.year}</td>
                                    <td>{p.processed ? 'Yes' : 'No'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </Table>
                )}
            </Card>
                </>
            )}
        </Container>
    );
};

export default NotebookDetail;
