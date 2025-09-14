import React from 'react';
import { Navbar, Nav, Container, Button } from 'react-bootstrap';
import { LinkContainer } from 'react-router-bootstrap';
import { useAuth } from '../contexts/AuthContext';

const Navigation: React.FC = () => {
    const { isAuthenticated, user, logout } = useAuth();

    if (!isAuthenticated) {
        return null; // Don't show navigation on login page
    }

    return (
        <Navbar bg="light" expand="lg" className="shadow-sm">
            <Container>
                <LinkContainer to="/">
                    <Navbar.Brand>
                        🔬 Hybrid Quantum AI
                    </Navbar.Brand>
                </LinkContainer>

                <Navbar.Toggle aria-controls="basic-navbar-nav" />

                <Navbar.Collapse id="basic-navbar-nav">
                    <Nav className="me-auto">
                        <LinkContainer to="/">
                            <Nav.Link>Dashboard</Nav.Link>
                        </LinkContainer>
                        <LinkContainer to="/reports/create">
                            <Nav.Link>Create Report</Nav.Link>
                        </LinkContainer>
                    </Nav>

                    <Nav className="ms-auto">
                        {user && (
                            <Navbar.Text className="me-3">
                                Welcome, {user.username}
                            </Navbar.Text>
                        )}
                        <Button
                            variant="outline-primary"
                            onClick={logout}
                            size="sm"
                        >
                            Logout
                        </Button>
                    </Nav>
                </Navbar.Collapse>
            </Container>
        </Navbar>
    );
};

export default Navigation;
