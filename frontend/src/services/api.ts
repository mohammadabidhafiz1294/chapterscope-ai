import axios, { AxiosResponse } from 'axios';

// API Base URL - adjust this to match your backend
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8001';

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
    created_by?: string;
    data?: ReportData[];
    visualizations?: Visualization[];
    export_history?: ExportJob[];
}

export interface ReportData {
    id: string;
    report_id: string;
    topic: string;
    prediction_score: number;
    confidence: number;
    trend: string;
    historical_data: Array<{
        year: number;
        frequency: number;
        percentage: number;
    }>;
    quantum_contribution?: number;
    classical_contribution?: number;
    created_at: string;
}

export interface Visualization {
    id: string;
    type: string;
    title: string;
    data: any;
    config: any;
}

export interface ExportJob {
    id: string;
    format: string;
    status: string;
    download_url?: string;
    file_size_bytes?: number;
    created_at: string;
}

export interface CreateReportRequest {
    title: string;
    description: string;
    topics: string[];
    prediction_year?: number;
    confidence_threshold?: number;
}

export interface UpdateReportRequest {
    title?: string;
    description?: string;
    topics?: string[];
    prediction_year?: number;
    confidence_threshold?: number;
}

export interface ReportListResponse {
    items: Report[];
    total: number;
    page: number;
    per_page: number;
    pages: number;
}

class ApiClient {
    constructor() {
        // Set up axios defaults
        axios.defaults.baseURL = API_BASE_URL;

        // Add request interceptor to include auth token
        axios.interceptors.request.use(
            (config) => {
                const token = localStorage.getItem('authToken');
                if (token) {
                    config.headers.Authorization = `Bearer ${token}`;
                }
                return config;
            },
            (error) => {
                return Promise.reject(error);
            }
        );

        // Add response interceptor to handle auth errors
        axios.interceptors.response.use(
            (response) => response,
            (error) => {
                if (error.response?.status === 401) {
                    // Token expired or invalid
                    localStorage.removeItem('authToken');
                    window.location.href = '/login';
                }
                return Promise.reject(error);
            }
        );
    }

    // Reports API
    async getReports(page = 1, perPage = 10, status?: string): Promise<ReportListResponse> {
        const params = new URLSearchParams({
            page: page.toString(),
            per_page: perPage.toString()
        });

        if (status) {
            params.append('status', status);
        }

        const response: AxiosResponse<ReportListResponse> = await axios.get(`/reports?${params}`);
        return response.data;
    }

    async getReport(id: string): Promise<Report> {
        const response: AxiosResponse<Report> = await axios.get(`/reports/${id}`);
        return response.data;
    }

    async createReport(data: CreateReportRequest): Promise<Report> {
        const response: AxiosResponse<Report> = await axios.post('/reports', data);
        return response.data;
    }

    async updateReport(id: string, data: UpdateReportRequest): Promise<Report> {
        const response: AxiosResponse<Report> = await axios.put(`/reports/${id}`, data);
        return response.data;
    }

    async deleteReport(id: string): Promise<void> {
        await axios.delete(`/reports/${id}`);
    }

    async generateReport(id: string): Promise<{ job_id: string; status: string; message: string }> {
        const response = await axios.post(`/reports/${id}/generate`);
        return response.data;
    }

    // Report Data API
    async getReportData(id: string): Promise<{ report_id: string; items: ReportData[]; total_count: number }> {
        const response = await axios.get(`/reports/${id}/data`);
        return response.data;
    }

    // Visualizations API
    async getReportVisualizations(id: string): Promise<{ report_id: string; visualizations: Visualization[] }> {
        const response = await axios.get(`/reports/${id}/visualizations`);
        return response.data;
    }

    // Export API
    async getReportExports(id: string): Promise<ExportJob[]> {
        const response = await axios.get(`/reports/${id}/export`);
        return response.data;
    }

    async createExport(id: string, format: 'pdf' | 'csv' | 'json'): Promise<{ export_id: string; status: string; format: string }> {
        const response = await axios.post(`/reports/${id}/export`, { format });
        return response.data;
    }

    // Authentication API (mock for now)
    async login(username: string, password: string): Promise<{ token: string; user: any }> {
        // Mock login - replace with actual API call
        if (username && password) {
            const mockUser = {
                id: '1',
                username: username,
                email: `${username}@example.com`
            };
            const mockToken = 'mock-jwt-token-' + Date.now();

            return {
                token: mockToken,
                user: mockUser
            };
        }
        throw new Error('Invalid credentials');
    }

    async register(username: string, email: string, password: string): Promise<{ token: string; user: any }> {
        // Mock registration - replace with actual API call
        const mockUser = {
            id: Date.now().toString(),
            username: username,
            email: email
        };
        const mockToken = 'mock-jwt-token-' + Date.now();

        return {
            token: mockToken,
            user: mockUser
        };
    }

    async validateToken(): Promise<{ user: any }> {
        // Mock token validation - replace with actual API call
        const mockUser = {
            id: '1',
            username: 'user',
            email: 'user@example.com'
        };

        return { user: mockUser };
    }
}

export const apiClient = new ApiClient();
export default apiClient;
