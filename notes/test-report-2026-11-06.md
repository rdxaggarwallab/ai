# Test Report: AI & Robotics LMS (2026-11-06)

**Tester:** the cloud testing session (independent of the build session).
**Code tested:** branch `claude/bot-performance-optimization-mj3rme` at `dff5c3f`.
**Scope:** static review of all backend and frontend code, the existing test suite, 39 new adversarial API tests,
7 autograder attacks in the real Docker sandbox, and a Playwright run of the `docs/TESTING.md` checklist
(Asia/Kolkata timezone, plus 390 px phone width).
**App code was not changed.** New test files are in `tests_e2e/` and screenshots are in `notes/test-report-2026-11-06/`.

## Summary

The basics work. Roles, per-course TAs, due dates in IST, the late penalty, closed submissions and the sandbox
limits (network, read-only filesystem, non-root) all behaved as described. The existing 20 tests pass.

However, **the autograder can't be trusted yet**, and a **teacher can be tricked into leaking the hidden tests and every
student's work**. Both need fixing before the pilot. A single shared login rate limit could also lock a whole class
out at the start of a lab.

| Severity | Count |
|---|---|
| Critical | 3 |
| High | 5 |
| Medium | 9 |
| Low | 10 |

## 1. Environment

| Item | Version / note |
|---|---|
| OS | Linux cloud container (not the Windows PC that `docs/TESTING.md` was written for) |
| Python | 3.13.18 (venv). Flask 3.1.0, Werkzeug 3.1.9, SQLAlchemy 2.1.8, Flask-Limiter 3.9.0, pytest 8.3.4 |
| PostgreSQL | 16.15 (local service). `flask db upgrade` and `flask db check` were clean |
| Docker | 29.9.2. `lms-grader:latest` built from mirror.gcr.io `python:3.12-slim` with pytest 8.3.4 and numpy 2.1.3 (workaround scratch Dockerfile) |
| Node / Vite | Node 22.23.4, Vite 5.4.11. Playwright 1.63.0 with Chromium |
| How it ran | `flask run -p 5000`, `AUTOGRADER=docker flask grade-worker`, and `npm run dev -- --port 3000`. **`docker compose up` was not tested** because image pulls are blocked here |
| Not possible here | numpy in the browser (jsDelivr is blocked, so the editor falls back to core Python, which is expected). Windows-specific paths were not exercised. |

## 2. Automated tests

**Existing suite** (`cd backend && python -m pytest -q -rs`): **20 passed, 0 skipped** (14 s, sandbox tests included).

**New adversarial suite** (`tests_e2e/`). Every test asserts the behaviour we *want*: `test_bug_*` tests fail because
of a real bug, and `test_guard_*` tests are attacks that are already blocked, kept as regression tests.

```
cd backend
python -m pytest -q ../tests_e2e -o pythonpath=../tests_e2e
LMS_TEST_DB=postgresql://lms:lms@localhost:5432/lms_test python -m pytest -q ../tests_e2e/test_adversarial.py -o pythonpath=../tests_e2e
```

| Run | Result |
|---|---|
| SQLite, all files (API + Docker sandbox) | 26 failed (all `test_bug_*`), 20 passed (all `test_guard_*`) |
| PostgreSQL, API file | 22 failed, 17 passed. The extra failure is `max_points: 10**12`, which is a 500 only on PostgreSQL (integer overflow) |

The guards that passed:
- Students can't read another student's file or code, and can't grade or regrade.
- An unenrolled student can't list assignments.
- A TA of course A can't create, edit, grade, download or list staff in course B, and can't add TAs.
- Teacher B can't edit teacher A's assignment.
- `points` values of −1, 101, NaN, ±inf, 1e309, null and "abc" are all rejected.
- A `../../etc/passwd.py` filename is stored safely, and `.exe` / `.py.exe` are rejected.
- A 21 MB upload gets a 413 response.
- The CSRF header is required and a wrong token is rejected.
- Hidden tests and the log are never sent to students.
- An honest wrong solution scores 1/2.
- Unicode in the solution source works.
- A 50 MB print is capped in the log.

`tests_e2e/browser_checklist.cjs` is the Playwright script for section 3.

## 3. Manual checklist (`docs/TESTING.md`, run with Playwright)

| # | Step | Result | Notes |
|---|---|---|---|
| 1 | Register teacher and student | ✅ | |
| 2 | Admin gives a user the TA role | ✅ | |
| 3 | Admin resets a password, user logs in with the new one | ⚠️ | The new password works, **but the student's already-open session keeps working** (H4) |
| 4 | 11th wrong password says "Too many attempts" | ⚠️ | Works, **but straight after, the *teacher* logging in with the correct password also got "Too many attempts"**: one bucket for everyone (H1) |
| 5 | Admin can't remove own admin role | ✅ | The dropdown is disabled |
| 6 | Course, enrolment, outsider blocked | ✅ | |
| 7 | Teacher adds a TA; TA opens and grades AI101 | ✅ | |
| 8 | TA can't manage a second course | ⚠️ | Blocked, but the direct URL tells the TA to "Enroll in this course", which a TA can't do (L2) |
| 9 | Due tomorrow 23:59 shows 23:59 local | ✅ | Shows "11:59:00 pm" and is stored as 18:29 UTC (IST browser) |
| 10 | Late submission, 20% penalty, TA grades 50 → 40 | ✅ | My grades shows `40/100 (50 − 20% late)` |
| 11 | Late work not accepted → "Submissions are closed" | ✅ | |
| 12 | `.exe` rejected; 25 MB rejected | ⚠️ | Both are rejected, but the 25 MB message is Werkzeug's "The data value transmitted exceeds the capacity limit." (L3). **Unicode filenames such as `उत्तर.pdf` are also rejected** (M1) |
| 13 | Code assignment with starter code and example tests | ✅ | |
| 14 | Editor shows starter code; `print("hi")` runs | ✅ | First run took 2.9 s (local Pyodide) |
| 15 | numpy in the browser | ⚠️ | Fails here because the CDN is blocked (expected in this environment, not counted as a bug) |
| 16 | `while True: pass` → Stop | ✅ | The page stays responsive. **But `print()` in a loop crashes the browser tab within about 1 s** (H2). `input()` gives a traceback (L4) |
| 17 | Wrong solution 0/2, correct one 2/2 · 10 pts | ✅ | Graded in about 2.3 s |
| 18 | Reload shows the last submitted code | ✅ | |
| 19 | Teacher sees prefilled grade, code, log; Regrade all | ✅ | **But a prefill like 66.67 can't be saved** (M2) |
| 20 | Student never sees hidden tests or the log | ✅ | Checked the page and all API responses. **But see C3**: a student can still get them through the teacher |
| 21 | Sandbox: `/etc` write and network blocked | ✅ | 0/2, and the host was unaffected |
| 21b | (extra) Forged score | ❌ | A wrong solution showed **"100/2 tests passed · 500 pts"** on a 10-point task, and the teacher's grade box was prefilled with 500 (C1, C2) |
| 22 | Phone width | ❌ | Horizontal scrolling on the course, grades and admin pages (M6) |
| 23 | Confusing, slow or ugly | ⚠️ | See L2, L3, L4, L8 |
| — | Console errors | ⚠️ | Only expected 4xx responses and a `prompt is not defined` error from `input()`. There were no React errors |

## 4. Bugs

### Critical

**C1. A student can forge a full autograder score.** File: `backend/app/grader.py:43-75`.
The student's code runs in the same process and container as pytest. It can overwrite `/tmp/junit.xml` after pytest
writes it, or patch pytest itself.
- Steps: submit this to a 2-test `add` task:
  ```python
  import atexit
  atexit.register(lambda: open("/tmp/junit.xml","w").write('<testsuite tests="2" failures="0" errors="0" skipped="0"/>'))
  def add(a, b): return 0
  ```
  Patching `_pytest.python.Function.runtest` to swallow `AssertionError` works too.
- Expected: 1/2 (5 pts). Actual: **2/2 (10 pts)**.
- Tests: `test_autograder_attacks.py::test_bug_wrong_solution_forges_full_score[atexit-junit|monkeypatch-pytest]`.
- The build notes call this an "acceptable known limit", but it takes two lines and needs no skill. Any student who
  searches for it will find it, and the score is prefilled as the teacher's grade.

**C2. The forged counts aren't checked, so scores can go above the maximum (or below zero).** Files: `grader.py:69-75` and `:186`.
- The XML `tests="2" failures="-98"` gives passed=100 and total=2.
- Expected: rejected, or clamped to the range 0..total. Actual: the student sees **"100/2 tests passed · 500 pts"** (10-point task), and
  `GradeForm` prefills 500 for the teacher. See `notes/test-report-2026-11-06/student-forged-score.png`.
- The same trick is a **covert channel**. Student code can read `test_solution.py` (it's in the same directory) and encode
  6 bytes per submission in `total`, so the hidden tests leak out over repeated submissions.
  Test: `test_bug_hidden_tests_leak_through_score`.

**C3. "Run" in the teacher's submission viewer runs student code with the teacher's session.** File: `frontend/src/pages/Course.jsx:294`
(`runnable={manage}`), together with `pyWorker.js`, a same-origin worker that sends cookies.
- Steps: a student submits code that runs `from js import fetch; await fetch("/api/courses/1/assignments")` and
  `/api/assignments/<id>/submissions`. The teacher opens **view** and presses **▶ Run**.
- Actual: the output shows **"STOLEN HIDDEN TESTS: # Hidden tests: …"** and **"ALL SUBMISSIONS VISIBLE: 5"**. See
  `teacher-run-steals-tests.png`. GET requests need no CSRF token, so the code could also send every student's code,
  grading logs and hidden tests to an outside server. The same applies to the starter-code editor in the teacher's own form.
- Expected: staff never run student code in the app's origin. Remove Run from the viewer, or run it in a sandboxed iframe
  (opaque origin, `credentials: "omit"`).

### High

**H1. One login and register rate-limit bucket for all users.** Files: `backend/app/extensions.py:11`, `backend/Dockerfile` (gunicorn `-w 2`).
- `get_remote_address` without `ProxyFix` means every request appears to come from the proxy (Vite, or the `web`
  container). Live result: 11 wrong attempts by one person, then **the teacher with the correct password got 429**.
- A class of 30 registering at the start of a lab gets 429 after the 5th registration in that minute.
- `memory://` storage under 2 gunicorn workers also means each worker counts separately (the real limit is about 2×).
- Test: `test_bug_rate_limit_shared_by_everyone_behind_proxy`.

**H2. `print()` in a loop crashes the student's browser tab.** File: `frontend/src/components/PythonEditor.jsx:344`.
- Each stdout batch is appended to React state with no cap. `i=0` / `while True: i+=1; print(i)`, then Run, and the
  tab crashed ("Page crashed") within about 1 s, before the 15 s limit or a Stop click could act. A beginner's
  common mistake loses their unsaved code.
- Expected: cap the output (for example 1,000 lines or 100 KB, then stop the worker) and throttle updates.

**H3. A demoted teacher keeps full control of their courses.** File: `backend/app/security.py:149-152`.
- `can_manage` checks `course.teacher_id == user.id` whatever the user's role. After an admin changes a teacher to
  `student`, `/api/courses/<id>` still says `can_manage: true`, and the user can still list all submissions with logs,
  download files and see staff.
- Test: `test_bug_demoted_teacher_still_manages_own_course`.

**H4. Sessions are never revoked.** Files: `backend/app/auth.py:56-60` and `admin.py:44-53`.
- JWTs are stateless and last 8 hours. Logout only deletes the cookie, a copied token keeps working, and an admin
  password reset doesn't end the attacker's session (confirmed live in step 3).
- Fix: add a `token_version` column checked in a `user_lookup`/blocklist callback, and bump it on reset, role change and logout.
- Tests: `test_bug_password_reset_does_not_end_existing_sessions`, `test_bug_logout_is_not_csrf_protected_and_does_not_revoke_token`.

**H5. The grade worker dies for good on a database error.** Files: `backend/app/grader.py:218-227`, `docker-compose.yml` (worker has no `restart:`).
- `claim_next()` and the commit in `grade_submission()` aren't protected by error handling. If Postgres restarts or the
  connection drops, the process exits, and every later submission stays "Autograder running…" indefinitely.
  Found by code review; not reproduced live.

### Medium

| # | Bug | Where | Repro / evidence |
|---|---|---|---|
| M1 | Non-ASCII filenames are rejected. `secure_filename("उत्तर.pdf")` returns `"pdf"`, which has no extension, so the upload gets 400 "File type not allowed". `résumé final.pdf` works but is renamed | `assignments.py:135` | Live upload in step 12b, and `test_bug_unicode_filename_rejected` |
| M2 | An autograder prefill like 66.67 (2 of 3 tests, 100 pts) can't be saved: the input has `step="0.5"`, and the browser says "nearest valid values are 66.5 and 67" | `Course.jsx:316` | Verified live; nothing was saved |
| M3 | Wrong JSON types crash with a 500 instead of a 400: login/register with a list or int, assignment `title: 123`, `description: {}`, `due_at: 1700000000`, `starter_code: []`, course `code: 123`, grade `feedback: {}`. On PostgreSQL also `max_points: 10**12` and course codes over 30 characters | `auth.py:47,22`, `assignments.py:61,66,101`, `courses.py:28`, `assignments.py:229` | `test_bug_*_type_confusion_*` |
| M4 | A regrade requested while a submission is `running` is lost: the worker later overwrites `pending` with `done` | `assignments.py:173,186` | Code review |
| M5 | No limit on submissions or uploads. 60 uploads in a row were all accepted, so 20 MB each can fill the disk. Every attempt also gets its own grade box | `assignments.py:105` | `test_bug_no_submission_limit_or_rate_limit` |
| M6 | Phone width (390 px): page scroll width is teacher course page 595 px, My grades 507 px, admin 468 px, student course 404 px. Tables and the grade form overflow, and the header bar doesn't stretch | `styles.css` (no `@media` for narrow screens) | `mobile-teacher_courses_1.png`, `mobile-student_grades.png` |
| M7 | Anyone can register as a teacher and create courses, and can then probe whether an email exists and its role through the Add TA errors | `auth.py:187`, `admin.py:259-263` | `test_bug_anyone_can_self_register_as_teacher` |
| M8 | Any student can enrol in any course (no key or approval) and see all its assignments | `courses.py:47-54` | Design gap |
| M9 | Deployment defaults: compose runs the **Vite dev server** for `web`, uses the dev JWT key by default, never sets `LMS_ENV=production` (so the secret-key guard never runs), and publishes API port 5000 directly | `docker-compose.yml`, `frontend/Dockerfile` | Config review |

### Low

| # | Bug | Where |
|---|---|---|
| L1 | Logout has no CSRF protection, so any site can log a user out | `auth.py:54` |
| L2 | A TA who opens an unassigned course is told to "Enroll in this course", which a TA can't do | `Course.jsx:35` |
| L3 | The 413 error text is Werkzeug's "The data value transmitted exceeds the capacity limit." Say "File is larger than 20 MB" | `__init__.py:63` |
| L4 | `input()` in the browser editor raises a long traceback (`prompt is not defined` in a worker). Give a friendly message or support stdin | `pyWorker.js` |
| L5 | `allow_late: "false"` (a string) is stored as True (`bool("false")`). The UI sends a boolean, but API clients won't | `assignments.py:81`, `test_bug_allow_late_string_false_is_treated_as_true` |
| L6 | Lowering `max_points` after grading leaves grades like **90/10** | `assignments.py:70`, `test_bug_lowering_max_points_leaves_grades_above_max` |
| L7 | No UI to edit or delete an assignment or course (`api.updateAssignment` exists but is never used), so a wrong due date can't be fixed | `Course.jsx` |
| L8 | The teacher sees every attempt with its own grade box, and nothing marks which attempt counts (latest or best) | `Course.jsx:254-274` |
| L9 | The submission `<dialog open>` is not modal: it overlaps the table and has no backdrop or Esc key | `Course.jsx:289` |
| L10 | Login skips argon2 for unknown emails, so timing reveals whether an email is registered (register's 409 reveals it anyway) | `auth.py:46-49` |

## 5. Top 5 fixes

1. **Make the autograder score trustworthy (C1, C2).** Never trust anything written inside the student's container.
   For example, run the hidden tests in a harness that calls the student's code in a *separate* process, and have the
   harness report through a channel the student process can't write to. At a minimum, clamp passed to 0..total, check
   that `total` equals the number of tests in the teacher's file, and make `/tmp/w` read-only to the student. Until
   then, label autograder points as "unverified" for the teacher.
2. **Stop running student code with staff credentials (C3).** Remove ▶ Run from `SubmissionViewer`, or run it in a
   sandboxed iframe with an opaque origin and no cookies.
3. **Fix the rate limiter (H1).** Use `ProxyFix` (trust one hop) and key login attempts by IP + email, with Redis (or the
   database) as shared storage for multiple gunicorn workers.
4. **Cap the editor output (H2)** at about 1,000 lines or 100 KB, terminate the worker when the cap is reached, and batch UI updates.
5. **Tighten auth (H3, H4).** `can_manage` should also require role teacher/admin (or ta + staff row). Add token
   revocation through a `token_version` bumped on password reset, role change and logout.

Next after those: M1 (Unicode filenames), M2 (`step="any"`), M3 (validate JSON types and return a 400 from a
`DataError` handler), H5 (worker error handling and a `restart: unless-stopped` policy), and M6 (mobile tables).
