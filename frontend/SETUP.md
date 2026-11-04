# LMS Frontend Setup Guide

## Quick Start

### 1. Install Dependencies
```bash
cd frontend
npm install
```

### 2. Start the Development Server
```bash
npm start
```

The app will open at `http://localhost:3000`

### 3. Make Sure Backend is Running
The frontend expects the backend API at `http://localhost:5000/api`

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
flask run
```

## Features Planned (MVP; not built yet, see docs/PLAN.md)

### ⬜ Authentication
- **Login Page:** Email and password login
- **Register Page:** Sign up as student or teacher
- **JWT Token Storage:** Automatic token management

### ⬜ Dashboard
- **Course Listing:** View all available courses
- **Course Enrollment:** Students can enroll in courses
- **User Profile:** Display user name and role
- **Logout:** Secure logout functionality

### ⬜ Styling
- Modern gradient design
- Responsive grid layout
- Smooth transitions and hover effects

## Pages

1. **Login** (`/login`) - User authentication
2. **Register** (`/register`) - New user registration
3. **Dashboard** (`/dashboard`) - Main app with courses

## API Integration

All API calls are handled through `src/api.js`:
- Auto-adds JWT token to requests
- Error handling
- Modular endpoints for auth, courses, assignments, grades

## Next Steps to Build (Step 3)

- [ ] Course Details page
- [ ] Assignments page
- [ ] Assignment submission form
- [ ] Grades/Marks view
- [ ] Teacher dashboard for creating courses/assignments
- [ ] File upload for assignments

## Testing

**Test Account:**
1. First, create a test account via Register
2. Use those credentials to login
3. Create a course (if teacher role)
4. Enroll in courses (if student role)

