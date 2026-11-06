# Setup Guide (Windows)

Your project folder is `D:\aair\.web\LMS`. Pick **one** of the two options below.

## Option 1: Docker (easiest)
Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), then:
```powershell
cd D:\aair\.web\LMS
docker compose up --build
```
Open http://localhost:3000. Press `Ctrl+C` to stop.
This starts 5 services: database, API, web app, the **grade worker** and a one-off build of the
**grader sandbox image** (`grader/Dockerfile`). Docker Desktop must be running, because the worker starts one
throwaway sandbox container per submission.
Your data is kept between runs. To erase everything: `docker compose down -v`.

## Option 2: Without Docker
You need **Python 3.11+**, **Node 20+** and **PostgreSQL 16**.

**1. Database** (once). In SQL Shell (psql) as the `postgres` user:
```sql
CREATE USER lms WITH PASSWORD 'lms';
CREATE DATABASE lms OWNER lms;
```

**2. Backend.** In terminal 1:
```powershell
cd D:\aair\.web\LMS\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
$env:FLASK_APP = "wsgi.py"
flask db upgrade          # creates the tables
flask run                 # API on http://localhost:5000
```

**3. Frontend.** In terminal 2:
```powershell
cd D:\aair\.web\LMS\frontend
npm install
npm run dev               # app on http://localhost:3000
```

**4. Autograder worker.** In terminal 3 (needs Docker Desktop for the sandbox):
```powershell
docker build -t lms-grader:latest D:\aair\.web\LMS\grader     # once
cd D:\aair\.web\LMS\backend
venv\Scripts\activate
$env:FLASK_APP = "wsgi.py"
flask grade-worker
```
No Docker? Set `$env:AUTOGRADER = "local-unsafe"` before `flask run` and `flask grade-worker`. That
runs student code **directly on your PC with no sandbox**. Only use it for your own test code.

**5. Run the tests** (backend terminal): `python -m pytest -q`
(The sandbox tests are skipped if Docker or the `lms-grader` image is missing.)

## Create the first admin
Admins can't sign up on the website. Create one from the backend terminal:
```powershell
flask create-admin you@institute.edu "Your Name"                       # without Docker
docker compose exec api flask create-admin you@institute.edu "Your Name"   # with Docker
```
It asks for a password. If the email already has an account, that account is promoted to admin.

## Try it
1. Create the admin (above). Register a second account and, as admin, open **Users** and make it a
   **teacher** (the sign-up page is for students only). Log in as the teacher, create a course, open it,
   and add an assignment. Note the course's **join code**.
2. In a private or incognito window, register as a **Student**, type the join code under **Join course**,
   open the course and upload a `.py` file.
3. Back as the teacher, refresh the page and enter a grade and feedback.
4. As the student, open **My grades**.
5. As admin, open **Users**, register a third person and change their role to **ta**. As the teacher,
   add them under **Teaching assistants** on the course page. The TA can now grade that course only.
6. Create an assignment with a due date in the past and a late penalty. The student's submission
   shows a **late** badge, and the grade shows the penalty.
7. **Coding assignment:** as the teacher, choose **Python code** as the type, add starter code, click
   **Insert example** under hidden tests (adjust it to match the starter code), and save. As the student,
   write code, press **▶ Run** to try it in the browser, then **Submit code**. Within a few seconds the
   grade shows "x/y tests passed". The teacher sees the score pre-filled, and **view** shows the code and test output.

## What works (MVP)
- ✅ Sign up as a student; admins make teachers and TAs. The token is in an httpOnly cookie with CSRF protection
- ✅ Logout and admin password reset end all of that user's sessions
- ✅ Courses: create (teacher); students join with the course's join code and only see their own courses
- ✅ Assignments: create with due date and points
- ✅ File submission (.py .ipynb .pdf .zip .txt .md .png .jpg, max 20 MB)
- ✅ Grading with feedback, and a student grades page
- ✅ Permission checks on the server: students see only their own work, teachers only their own courses
- ✅ Admin page: search users, change roles, reset passwords
- ✅ TAs assigned per course
- ✅ Due dates in the right timezone, late badge, late penalty %, or late work blocked
- ✅ Login limited to 10 tries a minute per person (per IP + email); submissions 10 a minute per student
- ✅ Attempt limit per assignment (default 20); the latest attempt counts
- ✅ Edit assignments after creating them

## What works (Phase 2: coding)
- ✅ Python editor in the browser with Run and Stop (an infinite loop or a print() loop can't freeze the page).
  The code runs with no network access, so it's safe for teachers to press Run on a student's code
- ✅ Hidden pytest tests, run on the server in a locked-down Docker sandbox. The student's code runs in a
  separate process under another user, so it can't read the tests or fake its score
- ✅ Automatic score (tests passed / total × points), pre-filled into the teacher's grade
- ✅ Teachers and TAs view the code and full test output; regrade one or all after fixing tests
- ✅ Students see "x/y tests passed" but never the hidden tests or their output
- ⚠️ numpy and other libraries in the browser need internet (loaded from the jsDelivr CDN).
  Plain Python works offline. On the server, add libraries to `grader/Dockerfile`.

## Settings (environment variables)
| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql://lms:lms@localhost:5432/lms` | |
| `LMS_ENV` | (unset) | Set to `production` on a real server: the app then refuses to start without a proper secret key |
| `JWT_SECRET_KEY` | dev key | **Must be changed** before real use: 32+ random characters |
| `COOKIE_SECURE` | `false` | Set to `true` when served over HTTPS |
| `UPLOAD_DIR` | `backend/uploads` | |
| `RATELIMIT_STORAGE_URI` | `memory://` | Use `redis://...` when running more than one server process, so limits are shared |
| `AUTOGRADER` | `docker` | `docker` (sandbox), `local-unsafe` (no sandbox, dev only, refused in production) or `off` |
| `GRADER_IMAGE` | `lms-grader:latest` | Sandbox image built from `grader/Dockerfile` |
| `GRADER_TIMEOUT` | `30` | Seconds a test run may take |
