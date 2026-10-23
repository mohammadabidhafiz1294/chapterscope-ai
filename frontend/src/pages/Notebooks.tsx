import React, { useState, useEffect } from 'react';
import {
    Container, Card, Button, Form, Alert, Spinner, Table, Badge,
} from 'react-bootstrap';
import { Link } from 'react-router-dom';
import {
    CourseNotebook, listNotebooks, createNotebook,
} from '../services/notebooks';

const Notebooks: React.FC = () => {
    const [notebooks, setNotebooks] = useState<CourseNotebook[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [showForm, setShowForm] = useState(false);
    const [title, setTitle] = useState('');
    const [courseCode, setCourseCode] = useState('');
    const [institution, setInstitution] = useState('');
    const [creating, setCreating] = useState(false);

    useEffect(() => {
        load();
    }, []);

    const load = async () => {
        try {
            setLoading(true);
            const response = await listNotebooks('active');
            setNotebooks(response.results);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load notebooks');
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!title.trim()) {
            setError('Title is required');
            return;
        }
        try {
            setCreating(true);
            setError('');
            await createNotebook({
                title: title.trim(),
                course_code: courseCode.trim(),
                institution: institution.trim(),
            });
            setTitle('');
            setCourseCode('');
            setInstitution('');
            setShowForm(false);
            await load();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create notebook');
        } finally {
            setCreating(false);
        }
    };

    if (loading) {
        return (
            <Container className="d-flex justify-content-center align-items-center" style={{ minHeight: '50vh' }}>
                <div className="text-center">
                    <Spinner animation="border" className="mb-3" />
                    <p>Loading notebooks...</p>
                </div>
            </Container>
        );
    }

    return (
        <Container>
            <div className="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h1 className="mb-2">📚 Course Notebooks</h1>
                    <p className="text-muted">
                        Each notebook scopes one course: syllabus, exam papers, questions and chat.
                    </p>
                </div>
                <Button variant="primary" onClick={() => setShowForm(!showForm)}>
                    {showForm ? 'Cancel' : '➕ New Notebook'}
                </Button>
            </div>

            {error && <Alert variant="danger">{error}</Alert>}

            {showForm && (
                <Card className="mb-4">
                    <Card.Body>
                        <Card.Title>Create a course notebook</Card.Title>
                        <Form onSubmit={handleCreate}>
                            <Form.Group className="mb-3">
                                <Form.Label>Title *</Form.Label>
                                <Form.Control
                                    value={title}
                                    onChange={(e) => setTitle(e.target.value)}
                                    placeholder="e.g. PH-401 Quantum Mechanics"
                                />
                            </Form.Group>
                            <Form.Group className="mb-3">
                                <Form.Label>Course code</Form.Label>
                                <Form.Control
                                    value={courseCode}
                                    onChange={(e) => setCourseCode(e.target.value)}
                                    placeholder="e.g. PH-401"
                                />
                            </Form.Group>
                            <Form.Group className="mb-3">
                                <Form.Label>Institution</Form.Label>
                                <Form.Control
                                    value={institution}
                                    onChange={(e) => setInstitution(e.target.value)}
                                    placeholder="e.g. Bilkent University"
                                />
                            </Form.Group>
                            <Button type="submit" variant="success" disabled={creating}>
                                {creating ? 'Creating...' : 'Create'}
                            </Button>
                        </Form>
                    </Card.Body>
                </Card>
            )}

            {notebooks.length === 0 ? (
                <Card body className="text-center text-muted">
                    No notebooks yet. Create one to get started.
                </Card>
            ) : (
                <Card>
                    <Table hover className="mb-0 align-middle">
                        <thead>
                            <tr>
                                <th>Title</th>
                                <th>Code</th>
                                <th>Institution</th>
                                <th>Status</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {notebooks.map((nb) => (
                                <tr key={nb.id}>
                                    <td>{nb.title}</td>
                                    <td>{nb.course_code || '—'}</td>
                                    <td>{nb.institution || '—'}</td>
                                    <td>
                                        <Badge bg={nb.is_archived ? 'secondary' : 'success'}>
                                            {nb.is_archived ? 'Archived' : 'Active'}
                                        </Badge>
                                    </td>
                                    <td className="text-end">
                                        <Link to={`/notebooks/${nb.id}`}>
                                            <Button size="sm" variant="outline-primary">
                                                Open
                                            </Button>
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </Table>
                </Card>
            )}
        </Container>
    );
};

export default Notebooks;
