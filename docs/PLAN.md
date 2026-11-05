# LMS Plan: AI & Robotics

## Goal
A learning management system (LMS) for AI and Robotics courses. Its main feature is a
safe place to write and run code, with automatic grading.

## Team
You (review, testing, deployment, decisions) and Claude (code, tests, docs).

## Stack
| Layer | Choice |
|---|---|
| Frontend | React with Vite (Node 20+) |
| Backend | Flask (Python 3.11+), SQLAlchemy, Flask-Migrate |
| Database | PostgreSQL |
| Auth | Passwords hashed with argon2. Session token (JWT) in an httpOnly cookie |
| Files | Local disk in development. S3 or MinIO in production |
| Grading jobs | `flask grade-worker` polls the database (no Redis needed) and runs each submission in a throwaway Docker container |
| In-browser Python | Pyodide in a Web Worker, CodeMirror editor |
| Notebooks | JupyterHub (Phase 3) |
| Dev / CI | Docker Compose, GitHub Actions |

## Roadmap
### MVP (3–4 weeks)
- [x] Docker Compose: database, API and web app (written, not yet tested on your PC)
- [x] Register and login with roles: admin, teacher, TA, student (students and teachers sign up themselves; admins are created with `flask create-admin`)
- [x] Admin screen: list and search users, change roles, reset passwords
- [x] TAs assigned per course by the course teacher or an admin
- [x] Courses: create (teacher), list, view details
- [x] Enrollment (student)
- [x] Assignments: create (teacher), upload a file to submit (student)
- [x] Due dates stored in UTC; late submissions marked, optional late penalty %, or late work blocked
- [x] Manual grading with feedback, and a grades page
- [x] GitHub Actions: backend tests, migration check on PostgreSQL, frontend build
- [ ] Deploy and pilot with a few users
- [ ] Password reset by email (admins reset passwords by hand for now)

### Phase 2: Coding (3–4 weeks)
- [x] Python editor in the browser (CodeMirror + Pyodide in a Web Worker): Run, Stop, 15s limit; works offline for core Python
- [x] Server-side autograder: hidden pytest tests in a Docker sandbox (no network, read-only, 256MB, 1 CPU, 64 processes, non-root, time limit); `flask grade-worker`; regrade one or all
- [ ] Tests students can see (public tests they run before submitting)
- [ ] Jupyter notebook (.ipynb) assignments
- [ ] Submission history, resubmission limits (late rules done in MVP)
- [~] Autograder score pre-fills the teacher's grade (full rubrics still to do)

### Phase 3: Compute (4–6 weeks)
- [ ] JupyterHub with a container per student (DockerSpawner)
- [ ] GPU quotas per course and student
- [ ] Code similarity check (MOSS or similar)

### Phase 4: Robotics & AI (4–6 weeks)
- [ ] Browser simulators (PyBullet, MuJoCo, Webots, Gazebo/ROS 2)
- [ ] Lab hardware booking
- [ ] Video submissions
- [ ] AI tutor that gives hints, not answers, and AI-drafted feedback a TA reviews

## Data model (MVP)
```
users        id, email, name, password_hash, role, created_at
courses      id, title, description, code, teacher_id -> users, created_at
enrollments  id, user_id -> users, course_id -> courses, created_at   (unique user+course)
assignments  id, course_id -> courses, title, description, due_at, max_points
submissions  id, assignment_id, student_id -> users, file_path, submitted_at
grades       id, submission_id (unique), points, feedback, graded_by -> users, graded_at
course_staff id, user_id -> users (role ta), course_id -> courses        (unique user+course)
assignments  + allow_late, late_penalty_percent, kind (file|code), starter_code, test_code (hidden)
submissions  + grading_status, tests_passed, tests_total, auto_points, grading_log (staff only)
```

## Security checklist
- [x] Passwords hashed with argon2; login limited to 10/min and register to 5/min per IP
- [x] Token in an httpOnly cookie with SameSite set, and CSRF protection
- [x] Permission checks on every API route (not only in the UI)
- [x] Uploads checked for type and size and stored outside the web root
- [x] `LMS_ENV=production` refuses to start without a real secret key and turns on Secure cookies
- [x] Student code only ever runs in a sandbox on the server (`AUTOGRADER=local-unsafe` is refused in production)
- [ ] Policy on how long student data is kept and who can see grades
