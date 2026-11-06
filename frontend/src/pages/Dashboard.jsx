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

  return (
    <>
      <h1>{user.role === "student" ? "My courses" : "Courses"}</h1>
      {error && <p className="error">{error}</p>}
      {user.role === "student" && <JoinCourse onJoined={load} />}
      {["teacher", "admin"].includes(user.role) && <NewCourse onCreated={load} />}
      {courses.length === 0 && <p className="muted">
        {user.role === "student" ? "You haven't joined a course yet. Ask your teacher for the join code."
          : user.role === "ta" ? "You haven't been added to a course yet." : "No courses yet."}</p>}
      <div className="grid">
        {courses.map((c) => (
          <div className="card" key={c.id}>
            <span className="tag">{c.code}</span>
            <h3>{c.title}</h3>
            <p className="muted">{c.description || "No description"}</p>
            <p className="muted small">Teacher: {c.teacher}</p>
            {c.join_code && <p className="small">Join code: <code className="joincode">{c.join_code}</code></p>}
            <Link className="button" to={`/courses/${c.id}`}>Open</Link>
          </div>
        ))}
      </div>
    </>
  );
}

function JoinCourse({ onJoined }) {
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setError(""); setMsg("");
    try {
      const c = await api.join(code.trim());
      setMsg(`Joined ${c.code}: ${c.title}`);
      setCode("");
      onJoined();
    } catch (err) { setError(err.message); }
  };
  return (
    <form className="card row" onSubmit={submit}>
      <input placeholder="Join code from your teacher" required value={code} aria-label="Join code"
        onChange={(e) => setCode(e.target.value.toUpperCase())} style={{ textTransform: "uppercase" }} />
      <button>Join course</button>
      {msg && <span className="ok">{msg}</span>}
      {error && <span className="error">{error}</span>}
    </form>
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
