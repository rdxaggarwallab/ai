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
- **Frontend:** React and Vite
- **Backend:** Python Flask, SQLAlchemy, Flask-Migrate
- **Database:** PostgreSQL
- **Code Execution:** Python and Jupyter (Phase 2, see the plan)

## Project Structure
```
ai/
├── backend/            # Flask API (app/, migrations/, tests/)
├── frontend/           # React app
├── docs/PLAN.md        # roadmap, data model, security checklist
├── notes/chat-log.md   # decisions and planning conversation
└── docker-compose.yml
```

## Getting Started
Fastest: `docker compose up --build`, then open http://localhost:3000.

Full instructions, including running without Docker on Windows: **[frontend/SETUP.md](frontend/SETUP.md)**.

## Status
MVP features work: login, courses, enrollment, assignments, file submission and grading.
Next up: see [docs/PLAN.md](docs/PLAN.md).

## Contributing
Work happens on feature branches merged into `main`. See `docs/PLAN.md` for the roadmap and `notes/chat-log.md` for decisions.
