import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    Alert, Badge, Button, Card, Form, ListGroup, Modal, Spinner,
} from 'react-bootstrap';
import {
    ChatApiError, ChatMessage, ChatSession, ChatSource,
    createChatSession, listChatMessages, listChatSessions, sendChatMessage,
} from '../services/chat';

interface Props {
    notebookId: number;
    archived: boolean;
}

const formatSource = (source: ChatSource): string => {
    const parts: string[] = [source.source_type.toLowerCase()];
    if (source.document_title) parts.push(source.document_title);
    if (source.year) parts.push(String(source.year));
    if (source.page_number) parts.push(`p.${source.page_number}`);
    if (source.question_number) parts.push(`Q${source.question_number}`);
    return parts.join(' · ');
};

const NotebookChat: React.FC<Props> = ({ notebookId, archived }) => {
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [session, setSession] = useState<ChatSession | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [loadingSessions, setLoadingSessions] = useState(true);
    const [loadingMessages, setLoadingMessages] = useState(false);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState('');
    const [selectedSource, setSelectedSource] = useState<ChatSource | null>(
        null
    );
    const scrollRef = useRef<HTMLDivElement>(null);

    // Load the session list once per notebook.
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                setLoadingSessions(true);
                const list = await listChatSessions(notebookId);
                if (!cancelled) setSessions(list);
            } catch (err) {
                if (!cancelled) {
                    setError(
                        err instanceof Error
                            ? err.message
                            : 'Failed to load chat sessions'
                    );
                }
            } finally {
                if (!cancelled) setLoadingSessions(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [notebookId]);

    // Load a session's history when one is selected.
    useEffect(() => {
        if (!session) {
            setMessages([]);
            return;
        }
        let cancelled = false;
        (async () => {
            try {
                setLoadingMessages(true);
                const history = await listChatMessages(notebookId, session.id);
                if (!cancelled) setMessages(history);
            } catch (err) {
                if (!cancelled) {
                    setError(
                        err instanceof Error
                            ? err.message
                            : 'Failed to load chat history'
                    );
                }
            } finally {
                if (!cancelled) setLoadingMessages(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [notebookId, session]);

    // Keep the newest turn in view.
    useEffect(() => {
        const node = scrollRef.current;
        if (node) node.scrollTop = node.scrollHeight;
    }, [messages, sending]);

    const handleNewSession = useCallback(async () => {
        try {
            setError('');
            const created = await createChatSession(notebookId);
            setSessions((prev) => [created, ...prev]);
            setSession(created);
        } catch (err) {
            setError(
                err instanceof Error ? err.message : 'Failed to create session'
            );
        }
    }, [notebookId]);

    const handleSend = useCallback(async () => {
        const content = input.trim();
        if (!content || !session || sending) return;
        setError('');
        setInput('');
        setSending(true);
        try {
            const exchange = await sendChatMessage(
                notebookId,
                session.id,
                content
            );
            setMessages((prev) => [
                ...prev,
                exchange.user_message,
                exchange.assistant_message,
            ]);
        } catch (err) {
            // The pipeline persists the user turn before retrieval/model, so
            // reconcile the transcript when the server says it was written.
            if (err instanceof ChatApiError && err.userMessage) {
                const persisted: ChatMessage = err.userMessage;
                setMessages((prev) => [...prev, persisted]);
            }
            setError(
                err instanceof Error ? err.message : 'Failed to send message'
            );
        } finally {
            setSending(false);
        }
    }, [input, session, sending, notebookId]);

    return (
        <>
            <Card>
                <Card.Header className="d-flex justify-content-between align-items-center">
                    <Card.Title as="h5" className="mb-0">
                        Notebook chat{' '}
                        <Badge bg="info" className="ms-2">grounded</Badge>
                    </Card.Title>
                    <Button
                        size="sm"
                        variant="outline-primary"
                        onClick={handleNewSession}
                        disabled={archived}
                    >
                        New session
                    </Button>
                </Card.Header>

                <Card.Body className="d-flex flex-column" style={{ minHeight: '420px' }}>
                    {archived && (
                        <Alert variant="warning">
                            This notebook is archived, so chat is read-only.
                        </Alert>
                    )}
                    {error && <Alert variant="danger">{error}</Alert>}

                    {loadingSessions ? (
                        <div className="text-center py-4">
                            <Spinner animation="border" />
                        </div>
                    ) : sessions.length === 0 ? (
                        <div className="text-center text-muted py-4">
                            No chat sessions yet. Start one to ask questions
                            grounded in this notebook's indexed sources.
                        </div>
                    ) : (
                        <>
                            <Form.Select
                                size="sm"
                                className="mb-3"
                                value={session ? session.id : ''}
                                onChange={(e) => {
                                    const id = parseInt(e.target.value, 10);
                                    const next =
                                        sessions.find((s) => s.id === id) ||
                                        null;
                                    setSession(next);
                                }}
                            >
                                <option value="">Select a session…</option>
                                {sessions.map((s) => (
                                    <option key={s.id} value={s.id}>
                                        {s.title || `Session ${s.id}`} (
                                        {s.message_count})
                                    </option>
                                ))}
                            </Form.Select>

                            {session && (
                                <div
                                    ref={scrollRef}
                                    className="flex-grow-1 mb-3"
                                    style={{
                                        overflowY: 'auto',
                                        maxHeight: '360px',
                                        border: '1px solid #dee2e6',
                                        borderRadius: '4px',
                                        padding: '0.75rem',
                                    }}
                                >
                                    {loadingMessages ? (
                                        <div className="text-center py-3">
                                            <Spinner animation="border" size="sm" />
                                        </div>
                                    ) : messages.length === 0 ? (
                                        <div className="text-muted text-center py-3">
                                            Ask a question to get started.
                                        </div>
                                    ) : (
                                        messages.map((msg) => (
                                            <div
                                                key={msg.id}
                                                className={`mb-2 p-2 rounded ${
                                                    msg.role === 'USER'
                                                        ? 'bg-primary bg-opacity-10 ms-4'
                                                        : 'bg-light me-4'
                                                }`}
                                            >
                                                <div className="d-flex justify-content-between">
                                                    <strong>
                                                        {msg.role === 'USER'
                                                            ? 'You'
                                                            : 'Assistant'}
                                                    </strong>
                                                    {msg.role === 'ASSISTANT' &&
                                                        msg.status ===
                                                            'insufficient_evidence' && (
                                                            <Badge bg="warning" text="dark">
                                                                insufficient evidence
                                                            </Badge>
                                                        )}
                                                </div>
                                                <div style={{ whiteSpace: 'pre-wrap' }}>
                                                    {msg.content}
                                                </div>
                                                {msg.role === 'ASSISTANT' &&
                                                    msg.sources.length > 0 && (
                                                        <div className="mt-1">
                                                            {msg.sources.map(
                                                                (source) => (
                                                                    <Button
                                                                        key={
                                                                            source.source_key
                                                                        }
                                                                        size="sm"
                                                                        variant="link"
                                                                        className="p-0 me-2 text-decoration-none"
                                                                        onClick={() =>
                                                                            setSelectedSource(
                                                                                source
                                                                            )
                                                                        }
                                                                    >
                                                                        {formatSource(
                                                                            source
                                                                        )}
                                                                    </Button>
                                                                )
                                                            )}
                                                        </div>
                                                    )}
                                            </div>
                                        ))
                                    )}
                                    {sending && (
                                        <div className="text-muted text-center py-2">
                                            <Spinner animation="border" size="sm" className="me-2" />
                                            Thinking…
                                        </div>
                                    )}
                                </div>
                            )}

                            <Form.Group>
                                <div className="d-flex gap-2">
                                    <Form.Control
                                        as="textarea"
                                        rows={2}
                                        value={input}
                                        placeholder={
                                            archived
                                                ? 'Archived notebooks are read-only.'
                                                : 'Ask about this notebook…'
                                        }
                                        disabled={!session || sending || archived}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (
                                                e.key === 'Enter' &&
                                                !e.shiftKey
                                            ) {
                                                e.preventDefault();
                                                handleSend();
                                            }
                                        }}
                                    />
                                    <Button
                                        variant="primary"
                                        disabled={
                                            !session ||
                                            sending ||
                                            archived ||
                                            !input.trim()
                                        }
                                        onClick={handleSend}
                                    >
                                        Send
                                    </Button>
                                </div>
                            </Form.Group>
                        </>
                    )}
                </Card.Body>
            </Card>

            <Modal
                show={selectedSource !== null}
                onHide={() => setSelectedSource(null)}
                size="lg"
            >
                <Modal.Header closeButton>
                    <Modal.Title>Source</Modal.Title>
                </Modal.Header>
                <Modal.Body>
                    {selectedSource && (
                        <>
                            <ListGroup className="mb-3">
                                <ListGroup.Item>
                                    <strong>Type:</strong>{' '}
                                    {selectedSource.source_type}
                                </ListGroup.Item>
                                <ListGroup.Item>
                                    <strong>Document:</strong>{' '}
                                    {selectedSource.document_title || '—'}
                                </ListGroup.Item>
                                {selectedSource.year && (
                                    <ListGroup.Item>
                                        <strong>Year:</strong>{' '}
                                        {selectedSource.year}
                                    </ListGroup.Item>
                                )}
                                {selectedSource.page_number && (
                                    <ListGroup.Item>
                                        <strong>Page:</strong>{' '}
                                        {selectedSource.page_number}
                                    </ListGroup.Item>
                                )}
                                {selectedSource.question_number && (
                                    <ListGroup.Item>
                                        <strong>Question:</strong>{' '}
                                        {selectedSource.question_number}
                                    </ListGroup.Item>
                                )}
                            </ListGroup>
                            <h6>Snippet</h6>
                            <p style={{ whiteSpace: 'pre-wrap' }}>
                                {selectedSource.snippet}
                            </p>
                            {selectedSource.quote && (
                                <>
                                    <h6>Cited quote</h6>
                                    <p
                                        className="border-start border-3 ps-2 fst-italic"
                                        style={{ whiteSpace: 'pre-wrap' }}
                                    >
                                        “{selectedSource.quote}”
                                    </p>
                                </>
                            )}
                        </>
                    )}
                </Modal.Body>
            </Modal>
        </>
    );
};

export default NotebookChat;
