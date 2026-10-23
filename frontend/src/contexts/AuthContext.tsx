import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import axios from 'axios';

interface User {
    id: number;
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

export const useAuth = (): AuthContextType => {
    const context = useContext(AuthContext);
    if (!context) throw new Error('useAuth must be used within an AuthProvider');
    return context;
};

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        axios.get('/api/auth/validate/', { withCredentials: true })
            .then((response) => setUser(response.data.user))
            .catch(() => setUser(null))
            .finally(() => setLoading(false));
    }, []);

    const login = async (username: string, password: string) => {
        setLoading(true);
        try {
            const response = await axios.post('/api/auth/login/', { username, password }, { withCredentials: true });
            setUser(response.data.user);
        } catch {
            throw new Error('Login failed. Please check your credentials.');
        } finally {
            setLoading(false);
        }
    };

    const register = async (username: string, email: string, password: string) => {
        setLoading(true);
        try {
            const response = await axios.post('/api/auth/register/', { username, email, password }, { withCredentials: true });
            setUser(response.data.user);
        } catch {
            throw new Error('Registration failed. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const logout = () => {
        void axios.post('/api/auth/logout/', {}, { withCredentials: true });
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, isAuthenticated: !!user, loading, login, logout, register }}>
            {children}
        </AuthContext.Provider>
    );
};
