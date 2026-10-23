import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Container } from 'react-bootstrap';
import Navigation from './components/Navigation';
import Login from './components/Login';
import Dashboard from './pages/Dashboard';
import ReportDetail from './pages/ReportDetail';
import CreateReport from './pages/CreateReport';
import Notebooks from './pages/Notebooks';
import NotebookDetail from './pages/NotebookDetail';
import NotebookPractice from './pages/NotebookPractice';
import GeneratedQuestionDetail from './pages/GeneratedQuestionDetail';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import './App.css';

// Protected Route component
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { isAuthenticated, loading } = useAuth();

    if (loading) {
        return (
            <Container className="d-flex justify-content-center align-items-center" style={{ minHeight: '100vh' }}>
                <div className="text-center">
                    <div className="loading-spinner mx-auto mb-3"></div>
                    <p>Loading...</p>
                </div>
            </Container>
        );
    }

    return isAuthenticated ? <>{children}</> : <Navigate to="/login" />;
};

function App() {
    return (
        <AuthProvider>
            <div className="app-container">
                <Navigation />
                <Container className="py-4">
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route
                            path="/"
                            element={
                                <ProtectedRoute>
                                    <Dashboard />
                                </ProtectedRoute>
                            }
                        />
                        <Route
                            path="/reports/create"
                            element={
                                <ProtectedRoute>
                                    <CreateReport />
                                </ProtectedRoute>
                            }
                        />
                        <Route
                            path="/reports/:id"
                            element={
                                <ProtectedRoute>
                                    <ReportDetail />
                                </ProtectedRoute>
                            }
                        />
                        <Route
                            path="/notebooks"
                            element={
                                <ProtectedRoute>
                                    <Notebooks />
                                </ProtectedRoute>
                            }
                        />
                        <Route
                            path="/notebooks/:id"
                            element={
                                <ProtectedRoute>
                                    <NotebookDetail />
                                </ProtectedRoute>
                            }
                        />
                        <Route
                            path="/notebooks/:id/practice"
                            element={
                                <ProtectedRoute>
                                    <NotebookPractice />
                                </ProtectedRoute>
                            }
                        />
                        <Route
                            path="/notebooks/:id/generated/:qid"
                            element={
                                <ProtectedRoute>
                                    <GeneratedQuestionDetail />
                                </ProtectedRoute>
                            }
                        />
                        <Route path="*" element={<Navigate to="/" />} />
                    </Routes>
                </Container>
            </div>
        </AuthProvider>
    );
}

export default App;
