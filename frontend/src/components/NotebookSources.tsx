import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Badge, Button, Card, Form, Spinner, Table } from 'react-bootstrap';
import {
    ExamPaperSummary, SyllabusSummary, listPapers, listSyllabi,
    retryPaperProcessing, uploadPaper, uploadSyllabus,
} from '../services/notebooks';

interface Props { notebookId: number; archived: boolean; }

const stateVariant = (state: string): string =>
    ({ PROCESSED: 'success', FAILED: 'danger', NEEDS_REVIEW: 'warning',
        OCR_REQUIRED: 'warning', PROCESSING: 'info' }[state] || 'secondary');

const NotebookSources: React.FC<Props> = ({ notebookId, archived }) => {
    const [syllabi, setSyllabi] = useState<SyllabusSummary[]>([]);
    const [papers, setPapers] = useState<ExamPaperSummary[]>([]);
    const [kind, setKind] = useState<'syllabus' | 'paper'>('paper');
    const [title, setTitle] = useState('');
    const [subject, setSubject] = useState('');
    const [year, setYear] = useState(new Date().getFullYear());
    const [file, setFile] = useState<File | null>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    const load = useCallback(async () => {
        try {
            const [syllabusResponse, paperResponse] = await Promise.all([
                listSyllabi(notebookId), listPapers(notebookId),
            ]);
            setSyllabi(syllabusResponse.results);
            setPapers(paperResponse.results as ExamPaperSummary[]);
            setError('');
        } catch {
            setError('Sources are unavailable. Check your connection or permissions and try again.');
        } finally { setLoading(false); }
    }, [notebookId]);
    useEffect(() => { void load(); }, [load]);

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!file || !title.trim() || (kind === 'syllabus' && !subject.trim())) {
            setError('Choose a file and complete the required metadata.');
            return;
        }
        setBusy(true); setError('');
        try {
            if (kind === 'syllabus') await uploadSyllabus(notebookId, { title: title.trim(), subject: subject.trim(), file });
            else await uploadPaper(notebookId, { title: title.trim(), year, file });
            setTitle(''); setSubject(''); setFile(null);
            const input = document.getElementById('source-file') as HTMLInputElement | null;
            if (input) input.value = '';
            await load();
        } catch {
            setError('Upload failed. Confirm the file type and try again.');
        } finally { setBusy(false); }
    };

    if (loading) return <div className="text-center py-5"><Spinner animation="border" /><p>Loading sources…</p></div>;
    return <div>
        {error && <Alert variant="danger" role="alert">{error}</Alert>}
        <Card className="mb-4">
            <Card.Header><Card.Title as="h5" className="mb-0">Add a source</Card.Title></Card.Header>
            <Card.Body>
                <Form onSubmit={submit}>
                    <div className="row g-3">
                        <Form.Group className="col-md-3">
                            <Form.Label>Source type</Form.Label>
                            <Form.Select value={kind} onChange={(e) => setKind(e.target.value as 'syllabus' | 'paper')} disabled={archived}>
                                <option value="paper">Exam paper</option><option value="syllabus">Syllabus</option>
                            </Form.Select>
                        </Form.Group>
                        <Form.Group className="col-md-4">
                            <Form.Label>Title</Form.Label>
                            <Form.Control value={title} onChange={(e) => setTitle(e.target.value)} disabled={archived} required />
                        </Form.Group>
                        {kind === 'syllabus' ? <Form.Group className="col-md-3">
                            <Form.Label>Subject</Form.Label>
                            <Form.Control value={subject} onChange={(e) => setSubject(e.target.value)} disabled={archived} required />
                        </Form.Group> : <Form.Group className="col-md-2">
                            <Form.Label>Year</Form.Label>
                            <Form.Control type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} disabled={archived} required />
                        </Form.Group>}
                        <Form.Group className="col-md-6">
                            <Form.Label>Document file</Form.Label>
                            <Form.Control id="source-file" type="file" accept=".pdf,.doc,.docx,.txt" onChange={(e) => setFile((e.target as HTMLInputElement).files?.[0] || null)} disabled={archived} required />
                            <Form.Text>PDF, DOC, DOCX or TXT.</Form.Text>
                        </Form.Group>
                    </div>
                    <Button className="mt-3" type="submit" disabled={archived || busy}>{busy ? 'Uploading…' : 'Upload source'}</Button>
                    {archived && <span className="text-muted ms-3">Archived notebooks are read-only.</span>}
                </Form>
            </Card.Body>
        </Card>
        <Card><Card.Header><Card.Title as="h5" className="mb-0">Documents</Card.Title></Card.Header>
            {syllabi.length + papers.length === 0 ? <Card.Body className="text-muted">No sources yet. Upload a syllabus or exam paper to begin.</Card.Body> :
                <Table responsive hover className="mb-0"><thead><tr><th>Title</th><th>Type</th><th>Metadata</th><th>Processing</th><th>Error</th><th /></tr></thead>
                    <tbody>{syllabi.map((item) => <tr key={`s${item.id}`}><td>{item.title}</td><td>Syllabus</td><td>{item.subject}</td><td><Badge bg={stateVariant(item.processing_status)}>{item.processing_status}</Badge></td><td>{item.processing_error || '—'}</td><td /></tr>)}
                        {papers.map((item) => <tr key={`p${item.id}`}><td>{item.title}</td><td>Exam paper</td><td>{item.year}{item.total_marks ? ` · ${item.total_marks} marks` : ''}</td><td><Badge bg={stateVariant(item.processing_status)}>{item.processing_status}</Badge></td><td>{item.processing_error || '—'}</td><td>{item.processing_status === 'FAILED' && <Button size="sm" variant="outline-danger" onClick={() => retryPaperProcessing(notebookId, item.id).then(load).catch(() => setError('Retry failed.'))} disabled={archived}>Retry</Button>}</td></tr>)}</tbody>
                </Table>}
        </Card>
    </div>;
};
export default NotebookSources;
