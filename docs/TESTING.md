# Testing Brief: LMS on the Windows PC

**Who this is for:** a Claude session running on the user's Windows PC (through Remote Control).
**Goal:** find out whether the LMS works on a real Windows machine, and report every problem clearly.
**Do not change the app's code.** Only test and report. Fixes happen in the build session.

## 0. Get the code
```powershell
# first time:
git clone -b claude/bot-performance-optimization-mj3rme https://github.com/rdxaggarwallab/ai.git D:\aair\.web\LMS
# if the folder already exists:
cd D:\aair\.web\LMS; git checkout claude/bot-performance-optimization-mj3rme; git pull
```
Read `frontend/SETUP.md` (setup) and `notes/chat-log.md` (background) first.

## 1. Environment check (record versions in the report)
`docker --version`, `docker compose version`, `git --version`, `python --version`, `node --version`.
Docker Desktop must be **running**. If something is missing, write it down and test whatever is possible.

## 2. Automated tests
```powershell
cd D:\aair\.web\LMS\backend
python -m venv venv; venv\Scripts\activate
pip install -r requirements.txt
docker build -t lms-grader:latest ..\grader
python -m pytest -q -rs
```
Expected: **20 passed**, none skipped. Report any failure with its full output.
Windows-specific code paths (local runner without Unix resource limits) have never run on Windows before,
so watch them closely.

## 3. Start the app with Docker
```powershell
cd D:\aair\.web\LMS
docker compose up --build
```
Expected: 5 services (db, api, web, worker, and grader-image, which exits after building).
Open http://localhost:3000. Record: first build time, errors in the logs, and whether `worker` prints
"Grade worker started (mode: docker)".

Create the admin:
`docker compose exec api flask create-admin admin@test.edu "Test Admin"` (password: `adminpass123`).

## 4. Manual checklist
Use separate browser profiles or incognito windows per role. Mark each step ✅ / ❌ / ⚠️.

**Accounts and roles**
1. Register a teacher (`t@test.edu`) and a student (`s@test.edu`), password `password123`.
2. Register `ta@test.edu`. As admin, open **Users** and change its role to `ta`.
3. As admin, reset the student's password, then log in with the new one.
4. Wrong password 11 times in a minute: the 11th must say "Too many attempts".
5. Admin can't remove their own admin role (the dropdown is disabled).

**Courses and TAs**
6. Teacher creates course `AI101`. The student enrolls. A second student who is *not* enrolled can't open it.
7. Teacher adds `ta@test.edu` under **Teaching assistants**. The TA can open and grade AI101.
8. Teacher creates a second course. The TA must **not** be able to manage it.

**File assignments, due dates, late work**
9. File assignment, due tomorrow 23:59. The displayed due time must be **23:59 local time** (check the PC's timezone).
10. File assignment with a due date in the past and a 20% penalty. The student submits: **late** badge.
    The TA grades 50 → "40 after late penalty". The student's **My grades** shows `40/100 (50 − 20% late)`.
11. Assignment in the past with "Accept late work" unticked: the student sees "Submissions are closed".
12. Upload a `.exe`: rejected. Upload a 25 MB file: rejected.

**Coding assignments (Phase 2)**
13. Teacher: type **Python code**, starter code `def add(a, b):\n    pass`, click **Insert example** for
    the tests, points 10, save.
14. Student: the editor shows the starter code. Write `print("hi")`, press **▶ Run**: "hi" appears.
    Note how long the first run takes (Python downloads the first time).
15. In the browser: `import numpy as np; print(np.arange(3))`. Expected to work with internet.
16. `while True: pass` → Run → **■ Stop** works and the page stays usable.
17. Submit a wrong solution: "Autograder running…", then "0/2 tests passed" within ~10 seconds.
    Submit a correct one: "2/2 tests passed · 10 pts".
18. Reload the page: the editor shows the last submitted code.
19. Teacher: the grade field is pre-filled with 10. **view** shows the code and pytest output. **Regrade all** works.
20. The student must never see the hidden tests or the pytest log (check the page and the network tab).
21. **Sandbox check:** submit this as the student. The tests should fail or error, and the PC must be unaffected:
    ```python
    import os, socket
    def add(a, b):
        open("/etc/x", "w")          # read-only filesystem
        socket.create_connection(("1.1.1.1", 53), timeout=3)   # no network
        return a + b
    ```

**General**
22. Try the app at phone width (DevTools device mode). Note anything broken.
23. Note anything confusing, slow or ugly, even if it "works".

## 5. Report
Write the results to `D:\aair\.web\LMS\notes\test-report-<date>.md`:
- Environment versions
- Automated tests: pass/fail counts, with full output of failures
- The checklist table with ✅/❌/⚠️ and notes
- **Bugs**: for each, the steps to reproduce, expected vs actual, and screenshots or log excerpts
- The top 3 things to fix first

Then commit and push the report only:
`git add notes/test-report-*.md; git commit -m "Test report"; git push`
If pushing isn't possible, leave the file. The user will pass it on.
Also send a short summary message back to the build session (`session_01ACNqF2wppnptWLJgMqKwxq`) if you can.
