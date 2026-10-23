import axios, { AxiosResponse } from 'axios';

const API_BASE_URL =
    process.env.REACT_APP_REPORTS_API_URL ||
    process.env.REACT_APP_API_URL ||
    'http://localhost:8001';
export const api = axios.create({ baseURL: API_BASE_URL, withCredentials: true });

export interface Report {
    id: string;
    title: string;
    description: string;
    topics: string[];
    status: 'pending' | 'processing' | 'completed' | 'failed';
    prediction_year?: number;
    confidence_threshold: number;
    created_at: string;
    updated_at: string;
}

export interface ReportData {
    id: string;
    report_id: string;
    topic: string;
    prediction_score: number;
    confidence: number;
    trend: string;
    historical_data: Array<{ year: number; frequency: number; percentage: number }>;
    quantum_contribution?: number;
    classical_contribution?: number;
    created_at: string;
}

export interface ReportListResponse {
    items: Report[];
    total: number;
    page: number;
    per_page: number;
    pages: number;
}

export interface CreateReportRequest {
    title: string;
    description: string;
    topics: string[];
    prediction_year?: number;
    confidence_threshold?: number;
}

class ApiClient {
    async getReports(page = 1, perPage = 10, status?: string): Promise<ReportListResponse> {
        const response = await api.get('/api/reports', {
            params: { page, per_page: perPage, ...(status ? { status } : {}) },
        });
        return response.data;
    }

    async getReport(id: string): Promise<Report> {
        const response: AxiosResponse<Report> = await api.get(`/api/reports/${id}`);
        return response.data;
    }

    async createReport(data: CreateReportRequest): Promise<Report> {
        const response: AxiosResponse<Report> = await api.post('/api/reports', data);
        return response.data;
    }

    async getReportData(id: string): Promise<{ items: ReportData[] }> {
        const response = await api.get(`/api/reports/${id}/data`);
        return response.data;
    }

    async generateReport(id: string): Promise<{ job_id: string; status: string }> {
        const response = await api.post(`/api/reports/${id}/generate`);
        return response.data;
    }

    async createExport(id: string, format: 'pdf' | 'csv' | 'json'): Promise<{ export_id: string }> {
        const response = await api.post(`/api/reports/${id}/export`, { format });
        return response.data;
    }
}

export const apiClient = new ApiClient();
export default apiClient;
