# Chat Log: LMS Planning

This file is the project's memory. Claude does not remember earlier sessions,
so every session adds its decisions and a summary of the conversation here.

**Setup:** you work on your PC in `D:\aair\.web\LMS` (a clone of this repo).
Claude builds in the cloud and pushes to GitHub. Run `git pull` to get updates.

---

## Session 1: 2026-11-03 / 04

**Q: "What do we have here?"**
The repo had docs only: `README.md`, `frontend/README.md`, `frontend/SETUP.md`
and `.gitignore`. There was no code. `SETUP.md` marked features as done that did
not exist, and the README mentioned a `develop` branch that does not exist.

**Q: "What can you add to the plan to make it good?"**
Suggested additions (now in [`docs/PLAN.md`](../docs/PLAN.md)):
- Decide build vs. adopt (Moodle, Canvas, Open edX with LTI). Decision: **build our own**.
- Safe code execution: JupyterLite in the browser first, then JupyterHub with a Docker container per student.
- Autograding with hidden tests (nbgrader or pytest), rubrics and a similarity check.
- Robotics: browser simulators (Webots, PyBullet, MuJoCo, Gazebo/ROS 2) and lab hardware booking.
- Write the data model down before coding. Use migrations, not a single `init.sql`.
- Security: argon2/bcrypt, httpOnly cookies, rate limits, permission checks on every route.
- Newer stack: Node 20+, Python 3.11+, Vite (not Create React App), Docker Compose, GitHub Actions.
- AI tutor that gives hints, not answers (later phase).
- A phased roadmap instead of one checklist.

**Q: "How much will it take us to develop?"**
For a 2-developer team, about 30–45 person-weeks (about 4–5 months).
Correction: hidden-test grading must run **on the server**, not in the browser.

**Q: "Only you and me."**
Claude writes the code. You review it, run it, decide, and handle deployment and users.
At about 10–15 hrs/week from you:
MVP 3–4 weeks, Phase 2 3–4 weeks, Phase 3 4–6 weeks, Phase 4 4–6 weeks. About 4 months total.
Advice: aim for MVP plus Phase 2 (about 2 months), pilot with one course, then decide on Phases 3–4.

**Q: "D:\aair\.web\LMS, we will build here."**
The cloud session cannot reach your PC. Chosen setup: Claude builds in the cloud and pushes,
and you clone or pull into `D:\aair\.web\LMS`:
```powershell
git clone https://github.com/rdxaggarwallab/ai.git D:\aair\.web\LMS
cd D:\aair\.web\LMS
git checkout claude/bot-performance-optimization-mj3rme
```

**Q: "Keep notes here, especially our chat, rest on cloud."**
Notes live in `notes/` (this file) and `docs/PLAN.md`, so they reach your D: folder on every pull.
Code is built in the cloud and pushed to GitHub.

**GitHub push failed:** Claude has no GitHub access to `rdxaggarwallab/ai` (403 error).
**Q: "Leave it, we will do it here."** We're building in this cloud session for now.
Claude sends files and a zip of the project to you directly. Save them into `D:\aair\.web\LMS`.

**MVP built (same session):**
- Backend `backend/`: Flask with SQLAlchemy and migrations, argon2 passwords, JWT in an httpOnly cookie
  with CSRF protection, and permission checks on every route. Uploads have a type whitelist and a 20 MB limit
  and are stored under random names.
- Frontend `frontend/`: React with Vite. Login, register, courses, enroll, assignments, upload, grading, My grades.
- `docker-compose.yml` with db, api and web.
- Verified: 5 backend tests pass, the migration was applied to a real PostgreSQL 16, and a browser test
  passed (teacher creates course and assignment, student enrolls and submits, teacher grades, student sees 92/100).
- Not verified: `docker compose up` (Docker Hub blocked downloads in the cloud machine). Try it on your PC.
- Fix along the way: SQLAlchemy 2.1 needs the `psycopg` (v3) driver, not `psycopg2`.

**Next session:** you run it on your PC (see `frontend/SETUP.md`) and report anything broken.
Then: an admin screen to manage users and roles, and the start of Phase 2 (in-browser Python and the autograder).

### Decisions so far
| # | Decision |
|---|---|
| 1 | Build our own LMS (not Moodle, Canvas or Open edX) |
| 2 | Team: you and Claude only |
| 3 | Local folder: `D:\aair\.web\LMS`. Code is built in the cloud and synced through GitHub |
| 4 | Working branch: `claude/bot-performance-optimization-mj3rme` |
| 5 | Target: MVP plus Phase 2 first, then a pilot |

### Open questions for you
- How many hours a week can you give?
- Where will it be hosted (institute server, a VPS, or a cloud provider)?
- How many students and courses will the pilot have?
