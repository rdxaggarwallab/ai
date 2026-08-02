# AI & Robotics Learning Management System (LMS)

A web-based LMS designed for AI and Robotics courses at your institute.

## Features
- Student login and registration
- Course browsing and enrollment
- Assignment submission
- Grading system
- Code editor integration
- Jupyter notebook support

## Tech Stack
- **Frontend:** React
- **Backend:** Python Flask
- **Database:** PostgreSQL
- **Code Execution:** Python, Jupyter

## Project Structure
```
ai/
├── frontend/          # React app
├── backend/           # Flask API
├── database/          # SQL schemas
├── docs/              # Documentation
└── README.md
```

## Getting Started

### Prerequisites
- Python 3.8+
- Node.js 14+
- PostgreSQL
- Git

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
flask run
```

### Frontend Setup
```bash
cd frontend
npm install
npm start
```

### Database Setup
```bash
cd database
psql -U postgres -f init.sql
```

## Next Steps
- [ ] Set up backend API
- [ ] Create database schema
- [ ] Build login page
- [ ] Build course listing
- [ ] Add assignment upload

## Contributing
Push to `develop` branch for new features.
