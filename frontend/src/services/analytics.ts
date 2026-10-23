import { client, write } from './notebooks';

// Phase 5 course analytics. Every number here is computed server-side from
// ORM rows (see backend README "Course analytics"); the client only renders
// and drives the label review queue. See `notebooks.ts` for why we use a
// dedicated axios instance with a relative baseURL.

export type Weighting = 'primary' | 'weighted';

export interface Coverage {
    weighting: string;
    secondary_weight: number;
    papers_total: number;
    papers_with_questions: number;
    questions_total: number;
    questions_classified: number;
    questions_unclassified: number;
    questions_with_marks: number;
    questions_with_type: number;
    questions_type_pending_review: number;
    topics_total: number;
    topics_confirmed: number;
    topics_needs_review: number;
    topics_with_questions: number;
    links_confirmed: number;
    links_pending_review: number;
    links_rejected: number;
    years_total: number;
    year_min: number | null;
    year_max: number | null;
    syllabus_documents: number;
    syllabi_with_text: number;
    [key: string]: number | string | null;
}

export interface TopicRow {
    id: number;
    name: string;
    aliases: string[];
    review_status: string;
    primary_questions: number;
    weighted_questions: number;
    distinct_questions: number;
    distinct_papers: number;
    paper_prevalence: number;
    question_share: number;
    raw_marks: number;
    normalized_marks: number;
    marks_share: number;
    recent_frequency: number;
    long_term_frequency: number;
    trend_slope: number | null;
    trend_direction: string;
    syllabus_importance: number;
    first_year: number | null;
    last_year: number | null;
    score: number;
    components: Record<string, number>;
    notices: string[];
    type_distribution: Record<string, number>;
}

export interface YearRow {
    year: number;
    papers: number;
    topic_prevalence: Record<string, number>;
}

export interface QuestionTypeCount {
    type: string;
    count: number;
}

export interface RankingMeta {
    disclaimer: string;
    weights: Record<string, number>;
    component_labels: Record<string, string>;
    trend_cap?: number;
}

export interface AnalyticsReport {
    notebook_id: number;
    definitions_version: string;
    generated_at: string;
    weighting: Weighting;
    coverage: Coverage;
    notices: string[];
    notice_labels: Record<string, string>;
    measure_labels: Record<string, string>;
    ranking: RankingMeta;
    topics: TopicRow[];
    topics_truncated: boolean;
    years: YearRow[];
    question_types: QuestionTypeCount[];
}

export interface TopicAnalyticsReport {
    notebook_id: number;
    definitions_version: string;
    weighting: Weighting;
    topic: TopicRow;
    links: {
        primary: number;
        secondary: number;
        pending_review: number;
        rejected: number;
    };
    years: Array<{
        year: number;
        papers: number;
        topic_papers: number;
        prevalence: number;
        weighted_questions: number;
        raw_marks: number;
    }>;
    notices: string[];
    notice_labels: Record<string, string>;
    measure_labels: Record<string, string>;
    ranking: RankingMeta;
    coverage: Coverage;
}

export interface PendingLink {
    id: number;
    question_id: number;
    question_number: string;
    text: string;
    topic_id: number;
    topic_name: string;
    role: 'PRIMARY' | 'SECONDARY';
    confidence: number | null;
    classification_source: string;
    review_status: string;
}

export interface PendingTopic {
    id: number;
    name: string;
    aliases: string[];
    review_status: string;
}

export interface PendingType {
    question_id: number;
    question_number: string;
    text: string;
    question_type: string;
    type_confidence: number | null;
    type_source: string;
}

export interface ReviewQueue {
    links: PendingLink[];
    topics: PendingTopic[];
    types: PendingType[];
}

export interface CreatedLink {
    id: number;
    question_id: number;
    topic_id: number;
    topic_name: string;
    role: 'PRIMARY' | 'SECONDARY';
    classification_source: string;
    classifier_version: string;
    confidence: number | null;
    review_status: string;
}

export interface ProposalsResult {
    notebook_id: number;
    used_llm: boolean;
    model: string;
    requested: number;
    threshold: number;
    links_created: CreatedLink[];
    topics_created: Array<{
        id: number;
        name: string;
        review_status: string;
    }>;
    types_proposed: Array<{
        question_id: number;
        question_type: string;
        confidence: number | null;
        applied: boolean;
    }>;
    unresolved: Array<{
        question_id: number;
        label: string;
        status: string;
        candidates: Array<{
            topic_id: number;
            name: string;
            score: number;
        }>;
    }>;
    low_confidence: Array<{
        question_id: number;
        labels: string[];
        confidence: number;
    }>;
    notices: string[];
}

export interface ReviewResult {
    links: Array<{ id: number; status: string }>;
    topics: Array<{ id: number; status: string }>;
    types: Array<{ question_id: number; status: string }>;
}

export interface TopicDetail {
    id: number;
    name: string;
    normalized_name: string;
    aliases: string[];
    description: string;
    review_status: string;
    created_at: string;
    updated_at: string;
}

export interface ApiError {
    error?: { code: string; message: string; hint?: string };
    detail?: string;
}

// Normalise every failure shape (analytics envelope, DRF validation, axios
// network errors) into one message for the UI.
export const apiErrorMessage = (err: unknown): string => {
    if (typeof err === 'object' && err !== null) {
        const data = (err as { response?: { data?: ApiError } }).response?.data;
        if (data?.error) {
            return data.error.hint
                ? `${data.error.message} ${data.error.hint}`
                : data.error.message;
        }
        if (typeof data?.detail === 'string') {
            return data.detail;
        }
        if (err instanceof Error && err.message) {
            return err.message;
        }
    }
    return 'Request failed';
};

export const getAnalytics = async (
    notebookId: number,
    params: { weighting?: Weighting; topics?: number } = {}
): Promise<AnalyticsReport> => {
    const response = await client.get(`/api/notebooks/${notebookId}/analytics/`, {
        params,
    });
    return response.data;
};

export const getTopicAnalytics = async (
    notebookId: number,
    topicId: number,
    weighting?: Weighting
): Promise<TopicAnalyticsReport> => {
    const response = await client.get(
        `/api/notebooks/${notebookId}/analytics/topics/${topicId}/`,
        { params: { weighting } }
    );
    return response.data;
};

export const getReviewQueue = async (
    notebookId: number
): Promise<ReviewQueue> => {
    const response = await client.get(
        `/api/notebooks/${notebookId}/analytics/review/`
    );
    return response.data;
};

export const runProposals = async (
    notebookId: number,
    body: { question_ids?: number[]; limit?: number; use_llm: boolean }
): Promise<ProposalsResult> =>
    write(async () => {
        const response = await client.post(
            `/api/notebooks/${notebookId}/analytics/proposals/`,
            body
        );
        return response.data;
    });

export const submitReview = async (
    notebookId: number,
    body: {
        links?: Array<{ id: number; action: 'confirm' | 'reject' }>;
        topics?: Array<{ id: number; action: 'confirm' | 'reject' }>;
        types?: Array<{
            question_id: number;
            action: 'confirm' | 'reject';
        }>;
    }
): Promise<ReviewResult> =>
    write(async () => {
        const response = await client.post(
            `/api/notebooks/${notebookId}/analytics/review/`,
            body
        );
        return response.data;
    });

export const assignTopicLink = async (
    notebookId: number,
    body: {
        question_id: number;
        topic_id: number;
        role?: 'PRIMARY' | 'SECONDARY';
        confidence?: number;
    }
): Promise<CreatedLink & { created: boolean }> =>
    write(async () => {
        const response = await client.post(
            `/api/notebooks/${notebookId}/analytics/links/`,
            body
        );
        return response.data;
    });
