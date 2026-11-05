import React, { createContext, useContext, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import { Login, Register } from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import CoursePage from "./pages/Course";
import Grades from "./pages/Grades";
import Admin from "./pages/Admin";
import "./styles.css";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

function App() {
  const [user, setUser] = useState(undefined); // undefined = still loading
  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null));
  }, []);
  if (user === undefined) return <p className="center">Loading…</p>;

  return (
    <AuthCtx.Provider value={{ user, setUser }}>
      <BrowserRouter>
        {user && <Nav />}
        <main>
          <Routes>
            <Route path="/login" element={user ? <Navigate to="/" /> : <Login />} />
            <Route path="/register" element={user ? <Navigate to="/" /> : <Register />} />
            <Route path="/" element={<Private><Dashboard /></Private>} />
            <Route path="/courses/:id" element={<Private><CoursePage /></Private>} />
            <Route path="/grades" element={<Private><Grades /></Private>} />
            <Route path="/admin" element={<Private role="admin"><Admin /></Private>} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </BrowserRouter>
    </AuthCtx.Provider>
  );
}

function Private({ children, role }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" />;
  if (role && user.role !== role) return <Navigate to="/" />;
  return children;
}

function Nav() {
  const { user, setUser } = useAuth();
  const nav = useNavigate();
  const logout = async () => {
    await api.logout();
    setUser(null);
    nav("/login");
  };
  return (
    <header className="nav">
      <Link to="/" className="brand">AI & Robotics LMS</Link>
      <nav>
        <Link to="/">Courses</Link>
        {user.role === "student" && <Link to="/grades">My grades</Link>}
        {user.role === "admin" && <Link to="/admin">Users</Link>}
        <span className="muted">{user.name} · {user.role}</span>
        <button className="link" onClick={logout}>Log out</button>
      </nav>
    </header>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
