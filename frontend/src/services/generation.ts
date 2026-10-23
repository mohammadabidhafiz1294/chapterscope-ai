import { client, write, Paginated } from './notebooks';

// Client for the Phase 7 practice-question generation endpoints. Reads reuse
// the shared `client`; the generate POST goes through `write()` so the Django
// CSRF token is attached (same convention as `notebooks.ts`). No provider
// secrets reach the browser.

export interface GenerationRequest {
    id: number;
    notebook: number;
    creator: number;
    topic: number | null;
    topic_name: string | null;
    topic_ids: number[];
    question_count: number;
    question_types: string[];
    difficulty: string;
    marks: number | null;
    language: string;
    include_answers: boolean;
    year_from: number | null;
    year_to: number | null;
    status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'PARTIAL' | 'FAILED';
    questions_created: number;
    questions_validated: number;
    questions_needs_review: number;
    generation_model: string;
    generation_version: string;
    request_meta: Record<string, unknown>;
    error_code: string;
    error_message: string;
    created_at: string;
    updated_at: string;
    finished_at: string | null;
}

export interface GeneratedSourceRef {
    source_key: string;
    source_type: string;
    document_title: string | null;
    question_number: string | null;
    year: number | null;
    page_number: number | null;
    quote: string;
}

export interface GeneratedQuestion {
    id: number;
    notebook: number;
    creator: number;
    request: number | null;
    source_question: number | null;
    topic: number | null;
    topic_name: string | null;
    topic_ids: number[];
    question_text: string;
    answer_text: string;
    solution_text: string;
    question_type: string;
    marks: number | null;
    difficulty: string;
    review_status: string;
    source_refs: GeneratedSourceRef[];
    language: string;
    marking_rubric: { criterion: string; marks: number }[];
    generation_model: string;
    generation_version: string;
    validation_status: 'VALIDATED' | 'NEEDS_REVIEW';
    validation_report: string[];
    answer_confidence: number | null;
    options: string[];
    numeric_report: Record<string, unknown>;
    created_at: string;
    updated_at: string;
}

export interface GenerationParams {
    topic_id: number;
    count?: number;
    question_types?: string[];
    difficulty?: string;
    marks?: number | null;
    language?: string;
    include_answers?: boolean;
    year_from?: number | null;
    year_to?: number | null;
}

// Canonical notebook topic (matches the Phase 5/7 topics endpoint).
export interface NotebookTopic {
    id: number;
    name: string;
    normalized_name: string;
    aliases: string[];
    description: string;
    review_status: string;
}

export const listTopics = async (
    notebookId: number
): Promise<NotebookTopic[]> => {
    const response = await client.get(
        `/api/notebooks/${notebookId}/topics/`
    );
    return (response.data as Paginated<NotebookTopic>).results;
};

export interface GenerationPayload {
    request: GenerationRequest;
    questions: GeneratedQuestion[];
}

// The pipeline's error body: `{error: {code, message, hint?}}`.
export interface GenerationErrorBody {
    error: { code: string; message: string; hint?: string };
}

export class GenerationApiError extends Error {
    code: string;
    hint?: string;

    constructor(body: GenerationErrorBody) {
        super(body.error?.message || 'Generation request failed');
        this.name = 'GenerationApiError';
        this.code = body.error?.code || 'unknown';
        this.hint = body.error?.hint;
    }
}

const toGenerationError = (err: any): GenerationApiError => {
    const body: GenerationErrorBody | undefined = err?.response?.data;
    if (body && body.error) {
        return new GenerationApiError(body);
    }
    // Network / unexpected failure — surface a stable code for the UI.
    return new GenerationApiError({
        error: { code: 'network', message: err?.message || 'Network error' },
    });
};

export const listGenerationRequests = async (
    notebookId: number
): Promise<GenerationRequest[]> => {
    const response = await client.get(
        `/api/notebooks/${notebookId}/generation/requests/`
    );
    return (response.data as Paginated<GenerationRequest>).results;
};

export const getGenerationRequest = async (
    notebookId: number,
    requestId: number
): Promise<GenerationRequest> => {
    const response = await client.get(
        `/api/notebooks/${notebookId}/generation/requests/${requestId}/`
    );
    return response.data as GenerationRequest;
};

export const getGeneratedQuestion = async (
    notebookId: number,
    questionId: number
): Promise<GeneratedQuestion> => {
    const response = await client.get(
        `/api/notebooks/${notebookId}/generation/questions/${questionId}/`
    );
    return response.data as GeneratedQuestion;
};

// Generate a small practice paper for one topic. Resolves with the created
// request and its questions. Rejects with `GenerationApiError` (code/hint).
export const generateQuestions = async (
    notebookId: number,
    params: GenerationParams
): Promise<GenerationPayload> =>
    write(async () => {
        try {
            const response = await client.post(
                `/api/notebooks/${notebookId}/generation/requests/`,
                params
            );
            return response.data as GenerationPayload;
        } catch (err) {
            throw toGenerationError(err);
        }
    });
