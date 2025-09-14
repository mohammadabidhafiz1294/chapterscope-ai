import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import axios from 'axios';

interface User {
    id: string;
    username: string;
    email: string;
}

interface AuthContextType {
    user: User | null;
    isAuthenticated: boolean;
    loading: boolean;
    login: (username: string, password: string) => Promise<void>;
    logout: () => void;
    register: (username: string, email: string, password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};

interface AuthProviderProps {
    children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Check if user is logged in on app start
        const token = localStorage.getItem('authToken');
        if (token) {
            // Validate token with backend
            validateToken(token);
        } else {
            setLoading(false);
        }
    }, []);

    const validateToken = async (token: string) => {
        try {
            // For now, we'll simulate token validation
            // In a real app, you'd call your backend API
            const response = await axios.get('/api/auth/validate/', {
                headers: { Authorization: `Bearer ${token}` }
            });
            setUser(response.data.user);
        } catch (error) {
            localStorage.removeItem('authToken');
        } finally {
            setLoading(false);
        }
    };

    const login = async (username: string, password: string) => {
        try {
            setLoading(true);
            // For now, we'll simulate login
            // In a real app, you'd call your backend API
            const response = await axios.post('/api/auth/login/', {
                username,
                password
            });

            const { token, user: userData } = response.data;
            localStorage.setItem('authToken', token);
            setUser(userData);

            // Set axios default header for future requests
            axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
        } catch (error) {
            throw new Error('Login failed. Please check your credentials.');
        } finally {
            setLoading(false);
        }
    };

    const register = async (username: string, email: string, password: string) => {
        try {
            setLoading(true);
            // For now, we'll simulate registration
            // In a real app, you'd call your backend API
            const response = await axios.post('/api/auth/register/', {
                username,
                email,
                password
            });

            const { token, user: userData } = response.data;
            localStorage.setItem('authToken', token);
            setUser(userData);

            // Set axios default header for future requests
            axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
        } catch (error) {
            throw new Error('Registration failed. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const logout = () => {
        localStorage.removeItem('authToken');
        delete axios.defaults.headers.common['Authorization'];
        setUser(null);
    };

    const value: AuthContextType = {
        user,
        isAuthenticated: !!user,
        loading,
        login,
        logout,
        register
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};
