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
| Grading jobs | Redis job queue (RQ) feeding a locked-down Docker runner (Phase 2) |
| Notebooks | JupyterLite in the browser (Phase 2), JupyterHub (Phase 3) |
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
- [ ] JupyterLite or Pyodide editor embedded in assignments
- [ ] Server-side autograder: tests students can see plus hidden tests (pytest/nbgrader) in a Docker sandbox with no network and CPU, memory and time limits
- [ ] Submission history, resubmission limits (late rules done in MVP)
- [ ] Rubrics that combine the automatic score with manual marks

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
assignments  + allow_late, late_penalty_percent
```

## Security checklist
- [x] Passwords hashed with argon2; login limited to 10/min and register to 5/min per IP
- [x] Token in an httpOnly cookie with SameSite set, and CSRF protection
- [x] Permission checks on every API route (not only in the UI)
- [x] Uploads checked for type and size and stored outside the web root
- [x] `LMS_ENV=production` refuses to start without a real secret key and turns on Secure cookies
- [ ] Student code only ever runs in a sandbox
- [ ] Policy on how long student data is kept and who can see grades
