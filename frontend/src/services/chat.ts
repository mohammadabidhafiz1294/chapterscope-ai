import { client, write, Paginated } from './notebooks';

// Client for the Phase 6 notebook chat endpoints. Reads reuse the shared
// `client`; writes go through `write()` so the Django CSRF token is attached
// (same convention as `notebooks.ts`). No provider secrets reach the browser.

export interface ChatSession {
    id: number;
    notebook: number;
    title: string;
    message_count: number;
    created_at: string;
    updated_at: string;
}

export interface ChatSource {
    source_key: string;
    source_type: string;
    document_title: string | null;
    page_number: number | null;
    question_number: string | null;
    year: number | null;
    snippet: string;
    similarity: number | null;
    quote: string;
}

export interface ChatMessage {
    id: number;
    session: number;
    role: 'USER' | 'ASSISTANT' | 'SYSTEM';
    content: string;
    sources: ChatSource[];
    status: string;
    created_at: string;
}

export interface ChatExchange {
    status: 'answered' | 'insufficient_evidence';
    user_message: ChatMessage;
    assistant_message: ChatMessage;
    sources: ChatSource[];
    meta: {
        status: string;
        model: string;
        request_id: string;
        retrieved: number;
        cited: number;
        retrieval_ms: number;
        llm_ms: number;
        took_ms: number;
    };
}

// The pipeline's error body: `{error: {code, message, hint?}, request_id?,
// user_message?}`. `user_message` is present only when the turn was already
// persisted (so the UI can reconcile its transcript).
export interface ChatErrorBody {
    error: { code: string; message: string; hint?: string };
    request_id?: string;
    user_message?: ChatMessage;
}

export class ChatApiError extends Error {
    code: string;
    hint?: string;
    requestId?: string;
    userMessage?: ChatMessage;

    constructor(body: ChatErrorBody) {
        super(body.error?.message || 'Chat request failed');
        this.name = 'ChatApiError';
        this.code = body.error?.code || 'unknown';
        this.hint = body.error?.hint;
        this.requestId = body.request_id;
        this.userMessage = body.user_message;
    }
}

const toChatError = (err: any): ChatApiError => {
    const body: ChatErrorBody | undefined = err?.response?.data;
    if (body && body.error) {
        return new ChatApiError(body);
    }
    // Network / unexpected failure — surface a stable code for the UI.
    return new ChatApiError({
        error: { code: 'network', message: err?.message || 'Network error' },
    });
};

export const listChatSessions = async (
    notebookId: number
): Promise<ChatSession[]> => {
    const response = await client.get(
        `/api/notebooks/${notebookId}/chat/sessions/`
    );
    return (response.data as Paginated<ChatSession>).results;
};

export const createChatSession = async (
    notebookId: number,
    title?: string
): Promise<ChatSession> =>
    write(async () => {
        try {
            const response = await client.post(
                `/api/notebooks/${notebookId}/chat/sessions/`,
                title ? { title } : {}
            );
            return response.data;
        } catch (err) {
            throw toChatError(err);
        }
    });

export const listChatMessages = async (
    notebookId: number,
    sessionId: number
): Promise<ChatMessage[]> => {
    const response = await client.get(
        `/api/notebooks/${notebookId}/chat/sessions/${sessionId}/messages/`
    );
    return (response.data as Paginated<ChatMessage>).results;
};

// One chat turn. Resolves with the full exchange (user + assistant + sources).
// Rejects with `ChatApiError` carrying `.code`, `.hint` and (when the user
// turn was already persisted) `.userMessage` for transcript reconciliation.
export const sendChatMessage = async (
    notebookId: number,
    sessionId: number,
    content: string
): Promise<ChatExchange> =>
    write(async () => {
        try {
            const response = await client.post(
                `/api/notebooks/${notebookId}/chat/sessions/${sessionId}/messages/`,
                { content }
            );
            return response.data as ChatExchange;
        } catch (err) {
            throw toChatError(err);
        }
    });
