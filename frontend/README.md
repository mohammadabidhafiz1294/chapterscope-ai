# ChapterScope AI Frontend

This is the React frontend for the Hybrid Quantum AI Exam Questions Analysis System.

## Features

- **Authentication**: Django session-cookie authentication with login/register
- **Dashboard**: View and manage prediction reports
- **Report Creation**: Create new analysis reports with topic selection
- **Report Details**: View detailed reports with interactive charts
- **Data Visualization**: Chart.js integration for prediction scores and historical trends
- **Export Functionality**: Export reports in PDF, CSV, and JSON formats
- **Responsive Design**: Bootstrap 5 responsive UI

## Tech Stack

- **React 18** with TypeScript
- **React Router** for navigation
- **Bootstrap 5** for styling
- **Chart.js** with react-chartjs-2 for visualizations
- **Axios** for API communication
- **Axios + Django session cookies**

## Getting Started

### Prerequisites

- Node.js 16+ and npm
- Backend API running on http://localhost:8000

### Installation

1. Install dependencies:
```bash
npm install
```

2. Start the development server:
```bash
npm start
```

3. Open [http://localhost:3000](http://localhost:3000) in your browser

### Build for Production

```bash
npm run build
```

## Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── Navigation.tsx   # Main navigation bar
│   └── Login.tsx        # Login/register forms
├── contexts/            # React contexts
│   └── AuthContext.tsx  # Authentication context
├── pages/               # Page components
│   ├── Dashboard.tsx    # Reports dashboard
│   ├── CreateReport.tsx # Report creation form
│   └── ReportDetail.tsx # Report details with charts
├── services/            # API services
│   └── api.ts           # API client and types
├── App.tsx              # Main app component
├── index.tsx            # App entry point
└── index.css            # Global styles
```

## API Integration

The frontend connects to the FastAPI backend running on port 8000. Make sure the backend is running before starting the frontend.

### Authentication Flow

1. User registers or logs in
2. Django creates an HttpOnly session cookie
3. API requests use `withCredentials` and CSRF protection for writes
4. The browser session is validated through `/api/auth/validate/`

### Key Endpoints

- `POST /auth/login` - User login
- `POST /auth/register` - User registration
- `GET /reports` - List user reports
- `POST /reports` - Create new report
- `GET /reports/{id}` - Get report details
- `POST /reports/{id}/generate` - Generate report
- `GET /reports/{id}/data` - Get report data
- `POST /exports` - Create export

## Development

### Available Scripts

- `npm start` - Start development server
- `npm build` - Build for production
- `npm test` - Run tests
- `npm eject` - Eject from Create React App

### Code Style

- TypeScript for type safety
- ESLint for code quality
- Prettier for code formatting
- React Hooks for state management

## Features in Detail

### Dashboard
- Paginated list of user reports
- Status indicators (pending, processing, completed, failed)
- Quick actions for each report
- Search and filter functionality

### Report Creation
- Topic selection with multi-select
- Prediction year configuration
- Real-time validation
- Success/error feedback

### Report Details
- Comprehensive report information
- Interactive charts for prediction scores
- Historical trend analysis
- Export options (PDF, CSV, JSON)
- Tabbed interface for different views

### Authentication
- Secure Django session-cookie and CSRF handling
- Protected routes
- Automatic logout on token expiration
- User registration and login forms

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Contributing

1. Follow the existing code style
2. Write TypeScript types for all data structures
3. Add proper error handling
4. Test components thoroughly
5. Update documentation as needed
