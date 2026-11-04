# LMS Frontend (React + Vite)

```bash
npm install
npm run dev     # http://localhost:3000
```

Requests to `/api` are proxied to the Flask backend at `http://localhost:5000`
(set `API_URL` to change it). See [SETUP.md](SETUP.md) for full setup.

## Structure
```
src/
  main.jsx         app, routes, nav, auth context
  api.js           all API calls (cookie auth + CSRF header)
  styles.css
  pages/
    Auth.jsx       login and register
    Dashboard.jsx  course list, create course, enroll
    Course.jsx     assignments, submit, grade
    Grades.jsx     student grades
```
