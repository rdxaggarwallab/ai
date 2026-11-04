import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../main";

export default function Dashboard() {
  const { user } = useAuth();
  const [courses, setCourses] = useState([]);
  const [error, setError] = useState("");
  const load = () => api.courses().then(setCourses).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const enroll = async (id) => {
    try { await api.enroll(id); load(); } catch (e) { setError(e.message); }
  };

  return (
    <>
      <h1>Courses</h1>
      {error && <p className="error">{error}</p>}
      {["teacher", "admin"].includes(user.role) && <NewCourse onCreated={load} />}
      {courses.length === 0 && <p className="muted">No courses yet.</p>}
      <div className="grid">
        {courses.map((c) => (
          <div className="card" key={c.id}>
            <span className="tag">{c.code}</span>
            <h3>{c.title}</h3>
            <p className="muted">{c.description || "No description"}</p>
            <p className="muted small">Teacher: {c.teacher}</p>
            {c.enrolled || c.can_manage ? (
              <Link className="button" to={`/courses/${c.id}`}>Open</Link>
            ) : user.role === "student" ? (
              <button onClick={() => enroll(c.id)}>Enroll</button>
            ) : null}
          </div>
        ))}
      </div>
    </>
  );
}

function NewCourse({ onCreated }) {
  const [form, setForm] = useState({ code: "", title: "", description: "" });
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.createCourse(form);
      setForm({ code: "", title: "", description: "" });
      onCreated();
    } catch (err) { setError(err.message); }
  };
  return (
    <form className="card row" onSubmit={submit}>
      <input placeholder="Code (e.g. AI101)" required value={form.code} onChange={set("code")} />
      <input placeholder="Title" required value={form.title} onChange={set("title")} />
      <input placeholder="Description" value={form.description} onChange={set("description")} />
      <button>Create course</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
