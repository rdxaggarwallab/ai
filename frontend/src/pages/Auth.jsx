import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../main";

export function Login() {
  const { setUser } = useAuth();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setUser(await api.login(form.email, form.password));
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <form className="card auth" onSubmit={submit}>
      <h1>Log in</h1>
      <input type="email" placeholder="Email" required value={form.email}
        onChange={(e) => setForm({ ...form, email: e.target.value })} />
      <input type="password" placeholder="Password" required value={form.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })} />
      {error && <p className="error">{error}</p>}
      <button>Log in</button>
      <p className="muted">No account? <Link to="/register">Register</Link></p>
    </form>
  );
}

export function Register() {
  const { setUser } = useAuth();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "student" });
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setUser(await api.register(form));
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <form className="card auth" onSubmit={submit}>
      <h1>Create account</h1>
      <input placeholder="Full name" required value={form.name} onChange={set("name")} />
      <input type="email" placeholder="Email" required value={form.email} onChange={set("email")} />
      <input type="password" placeholder="Password (min 8 characters)" required minLength={8}
        value={form.password} onChange={set("password")} />
      <select value={form.role} onChange={set("role")}>
        <option value="student">Student</option>
        <option value="teacher">Teacher</option>
      </select>
      {error && <p className="error">{error}</p>}
      <button>Register</button>
      <p className="muted">Have an account? <Link to="/login">Log in</Link></p>
    </form>
  );
}
