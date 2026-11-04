import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";

export default function CoursePage() {
  const { id } = useParams();
  const [course, setCourse] = useState(null);
  const [assignments, setAssignments] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const c = await api.course(id);
      setCourse(c);
      if (c.can_view) setAssignments(await api.assignments(id));
    } catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, [id]);

  if (error) return <p className="error">{error}</p>;
  if (!course) return <p>Loading…</p>;
  if (!course.can_view) return <p className="muted">Enroll in this course to see it.</p>;

  return (
    <>
      <span className="tag">{course.code}</span>
      <h1>{course.title}</h1>
      <p className="muted">{course.description}</p>
      {course.can_manage && <NewAssignment courseId={id} onCreated={load} />}
      <h2>Assignments</h2>
      {assignments.length === 0 && <p className="muted">No assignments yet.</p>}
      {assignments.map((a) => (
        <Assignment key={a.id} a={a} manage={course.can_manage} />
      ))}
    </>
  );
}

function NewAssignment({ courseId, onCreated }) {
  const empty = { title: "", description: "", due_at: "", max_points: 100 };
  const [form, setForm] = useState(empty);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await api.createAssignment(courseId, { ...form, due_at: form.due_at || null });
      setForm(empty);
      onCreated();
    } catch (err) { setError(err.message); }
  };
  return (
    <form className="card row" onSubmit={submit}>
      <input placeholder="Assignment title" required value={form.title} onChange={set("title")} />
      <input placeholder="Instructions" value={form.description} onChange={set("description")} />
      <label className="small">Due <input type="datetime-local" value={form.due_at} onChange={set("due_at")} /></label>
      <label className="small">Points <input type="number" min="1" value={form.max_points}
        onChange={set("max_points")} style={{ width: 80 }} /></label>
      <button>Add assignment</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

function Assignment({ a, manage }) {
  const [subs, setSubs] = useState([]);
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState("");
  const load = () => api.submissions(a.id).then(setSubs).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, [a.id]);

  const upload = async (e) => {
    e.preventDefault();
    if (!file) return;
    try {
      await api.submit(a.id, file);
      setMsg("Submitted ✓");
      setFile(null);
      e.target.reset();
      load();
    } catch (err) { setMsg(err.message); }
  };

  return (
    <div className="card">
      <h3>{a.title} <span className="muted small">· {a.max_points} pts
        {a.due_at && ` · due ${new Date(a.due_at).toLocaleString()}`}</span></h3>
      <p>{a.description}</p>

      {!manage && (
        <form className="row" onSubmit={upload}>
          <input type="file" accept=".py,.ipynb,.pdf,.zip,.txt,.md,.png,.jpg"
            onChange={(e) => setFile(e.target.files[0])} />
          <button disabled={!file}>Submit</button>
        </form>
      )}
      {msg && <p className="muted">{msg}</p>}

      {subs.length > 0 && (
        <table>
          <thead><tr>
            {manage && <th>Student</th>}<th>File</th><th>Submitted</th><th>Grade</th>
          </tr></thead>
          <tbody>
            {subs.map((s) => (
              <tr key={s.id}>
                {manage && <td>{s.student}</td>}
                <td><a href={api.fileUrl(s.id)}>{s.original_name}</a></td>
                <td className="small">{new Date(s.submitted_at).toLocaleString()}</td>
                <td>{manage ? <GradeForm s={s} max={a.max_points} onSaved={load} />
                  : s.grade ? `${s.grade.points}/${a.max_points} ${s.grade.feedback ? "· " + s.grade.feedback : ""}`
                  : <span className="muted">Not graded</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function GradeForm({ s, max, onSaved }) {
  const [points, setPoints] = useState(s.grade?.points ?? "");
  const [feedback, setFeedback] = useState(s.grade?.feedback ?? "");
  const [err, setErr] = useState("");
  const save = async (e) => {
    e.preventDefault();
    try { await api.grade(s.id, points, feedback); setErr(""); onSaved(); }
    catch (x) { setErr(x.message); }
  };
  return (
    <form className="row" onSubmit={save}>
      <input type="number" min="0" max={max} step="0.5" required value={points}
        onChange={(e) => setPoints(e.target.value)} style={{ width: 70 }} />
      <input placeholder="Feedback" value={feedback} onChange={(e) => setFeedback(e.target.value)} />
      <button>{s.grade ? "Update" : "Save"}</button>
      {err && <span className="error">{err}</span>}
    </form>
  );
}
