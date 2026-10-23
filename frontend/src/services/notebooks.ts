import axios, { AxiosInstance } from 'axios';

// Notebook APIs are served by Django through the CRA development proxy.
// Keep this client relative so it is not coupled to the legacy report service.
export const client: AxiosInstance = axios.create({
    baseURL: '',
    withCredentials: true,
});

export interface CourseNotebook {
    id: number;
    title: string;
    course_code: string;
    institution: string;
    description: string;
    status: 'ACTIVE' | 'ARCHIVED';
    archived_at: string | null;
    is_archived: boolean;
    syllabus_count: number;
    paper_count: number;
    question_count: number;
    created_at: string;
    updated_at: string;
}

export interface Paginated<T> {
    count: number;
    results: T[];
}

export interface CreateNotebookRequest {
    title: string;
    course_code?: string;
    institution?: string;
    description?: string;
}

export interface SyllabusSummary {
    id: number;
    title: string;
    subject: string;
    processed: boolean;
    processed_at: string | null;
    topic_count: number;
    uploaded_at: string;
    has_file: boolean;
    notebook: number;
    content_hash: string;
    processing_status: string;
    processing_error: string;
}

export interface ExamPaperSummary {
    id: number;
    title: string;
    year: number;
    total_marks: number | null;
    processed: boolean;
    processed_at: string | null;
    question_count: number;
    topic_count: number;
    uploaded_at: string;
    has_file: boolean;
    notebook: number;
    content_hash: string;
    processing_status: string;
    processing_error: string;
}

let csrfToken: string | null = null;

const ensureCsrf = async (): Promise<void> => {
    if (csrfToken) return;
    const response = await client.get('/api/auth/csrf-token/');
    csrfToken = response.data.csrf_token;
    client.defaults.xsrfCookieName = 'csrftoken';
    client.defaults.xsrfHeaderName = 'X-CSRFToken';
};

export const write = async <T,>(fn: () => Promise<T>): Promise<T> => {
    await ensureCsrf();
    return fn();
};

export const listNotebooks = async (
    status: 'active' | 'archived' | 'all' = 'active',
    page = 1
): Promise<Paginated<CourseNotebook>> => {
    const response = await client.get('/api/notebooks/', {
        params: { status, page },
    });
    return response.data;
};

export const getNotebook = async (id: number): Promise<CourseNotebook> => {
    const response = await client.get(`/api/notebooks/${id}/`);
    return response.data;
};

export const createNotebook = async (
    data: CreateNotebookRequest
): Promise<CourseNotebook> =>
    write(async () => {
        const response = await client.post('/api/notebooks/', data);
        return response.data;
    });

export const updateNotebook = async (
    id: number,
    data: Partial<CreateNotebookRequest>
): Promise<CourseNotebook> =>
    write(async () => {
        const response = await client.patch(`/api/notebooks/${id}/`, data);
        return response.data;
    });

export const archiveNotebook = async (id: number): Promise<CourseNotebook> =>
    write(async () => {
        const response = await client.post(`/api/notebooks/${id}/archive/`);
        return response.data;
    });

export const unarchiveNotebook = async (id: number): Promise<CourseNotebook> =>
    write(async () => {
        const response = await client.post(`/api/notebooks/${id}/unarchive/`);
        return response.data;
    });

export const deleteNotebook = async (id: number): Promise<void> =>
    write(async () => {
        await client.delete(`/api/notebooks/${id}/`);
    });

export const listPapers = async (notebookId: number): Promise<Paginated<any>> => {
    const response = await client.get(`/api/notebooks/${notebookId}/papers/`);
    return response.data;
};

export const listSyllabi = async (
    notebookId: number
): Promise<Paginated<SyllabusSummary>> => {
    const response = await client.get(`/api/notebooks/${notebookId}/syllabi/`);
    return response.data;
};

export const uploadSyllabus = async (
    notebookId: number,
    data: { title: string; subject: string; file: File }
): Promise<SyllabusSummary> =>
    write(async () => {
        const form = new FormData();
        form.append('title', data.title);
        form.append('subject', data.subject);
        form.append('file', data.file);
        const response = await client.post(
            `/api/notebooks/${notebookId}/syllabi/upload/`,
            form
        );
        return response.data;
    });

export const uploadPaper = async (
    notebookId: number,
    data: { title: string; year: number; total_marks?: number; file: File }
): Promise<ExamPaperSummary> =>
    write(async () => {
        const form = new FormData();
        form.append('title', data.title);
        form.append('year', String(data.year));
        if (data.total_marks) form.append('total_marks', String(data.total_marks));
        form.append('file', data.file);
        const response = await client.post(
            `/api/notebooks/${notebookId}/papers/upload/`,
            form
        );
        return response.data;
    });

export const retryPaperProcessing = async (
    notebookId: number,
    paperId: number
): Promise<unknown> =>
    write(async () => {
        const response = await client.post(
            `/api/notebooks/${notebookId}/papers/${paperId}/process/`
        );
        return response.data;
    });

export const listQuestions = async (
    notebookId: number,
    params: Record<string, string | number>
): Promise<Paginated<{
    id: number; exam_paper_title: string; question_number: string;
    raw_text: string; page_reference: string | null; source_page_number: number | null;
    marks: number | null; year: number; question_type: string;
    difficulty: string; extraction_status: string;
}>> => {
    const response = await client.get(`/api/notebooks/${notebookId}/questions/`, { params });
    return response.data;
};

export const attachPaper = async (
    notebookId: number,
    paperId: number
): Promise<any> =>
    write(async () => {
        const response = await client.post(
            `/api/notebooks/${notebookId}/papers/`,
            { paper_id: paperId }
        );
        return response.data;
    });
