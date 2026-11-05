import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../main";
import PythonEditor from "../components/PythonEditor";

const SAMPLE_TESTS = `# Hidden tests: students never see this. Their code is saved as solution.py.
from solution import add

def test_add():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-1, 1) == 0
`;

export default function CoursePage() {
  const { id } = useParams();
  const { user } = useAuth();
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

  // Only the course's own teacher or an admin assigns TAs.
  const ownsCourse = user.role === "admin" || course.teacher_id === user.id;

  return (
    <>
      <span className="tag">{course.code}</span>
      <h1>{course.title}</h1>
      <p className="muted">{course.description}</p>
      {ownsCourse && <Staff courseId={id} />}
      {course.can_manage && <NewAssignment courseId={id} onCreated={load} />}
      <h2>Assignments</h2>
      {assignments.length === 0 && <p className="muted">No assignments yet.</p>}
      {assignments.map((a) => (
        <Assignment key={a.id} a={a} manage={course.can_manage} />
      ))}
    </>
  );
}

function Staff({ courseId }) {
  const [staff, setStaff] = useState([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const load = () => api.staff(courseId).then(setStaff).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [courseId]);

  const add = async (e) => {
    e.preventDefault();
    setError("");
    try { await api.addStaff(courseId, email); setEmail(""); load(); }
    catch (err) { setError(err.message); }
  };
  const remove = async (u) => {
    setError("");
    try { await api.removeStaff(courseId, u.id); load(); } catch (err) { setError(err.message); }
  };

  return (
    <div className="card">
      <h3>Teaching assistants</h3>
      <div className="staff">
        {staff.length === 0 && <span className="muted small">No TAs yet.</span>}
        {staff.map((u) => (
          <span className="chip" key={u.id}>{u.name}
            <button title={`Remove ${u.name}`} aria-label={`Remove ${u.name}`} onClick={() => remove(u)}>✕</button>
          </span>
        ))}
      </div>
      <form className="row" onSubmit={add} style={{ marginTop: 12 }}>
        <input type="email" placeholder="TA's email" required value={email}
          onChange={(e) => setEmail(e.target.value)} />
        <button>Add TA</button>
        {error && <span className="error">{error}</span>}
      </form>
    </div>
  );
}

function NewAssignment({ courseId, onCreated }) {
  const empty = { title: "", description: "", due_at: "", max_points: 100,
    allow_late: true, late_penalty_percent: 0, kind: "file", starter_code: "", test_code: "" };
  const [form, setForm] = useState(empty);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      // datetime-local is the teacher's local time; send it as UTC so the deadline is exact.
      const due_at = form.due_at ? new Date(form.due_at).toISOString() : null;
      await api.createAssignment(courseId, { ...form, due_at });
      setForm(empty);
      onCreated();
    } catch (err) { setError(err.message); }
  };
  return (
    <form className="card stack" onSubmit={submit}>
      <div className="row">
      <input placeholder="Assignment title" required value={form.title} onChange={set("title")} />
      <select value={form.kind} onChange={set("kind")} aria-label="Assignment type">
        <option value="file">File upload</option>
        <option value="code">Python code (editor + autograder)</option>
      </select>
      <input placeholder="Instructions" value={form.description} onChange={set("description")} />
      <label className="small">Due <input type="datetime-local" value={form.due_at} onChange={set("due_at")} /></label>
      <label className="small">Points <input type="number" min="1" value={form.max_points}
        onChange={set("max_points")} style={{ width: 80 }} /></label>
      <label className="small"><input type="checkbox" checked={form.allow_late} onChange={set("allow_late")} /> Accept late work</label>
      {form.allow_late && (
        <label className="small">Late penalty % <input type="number" min="0" max="100"
          value={form.late_penalty_percent} onChange={set("late_penalty_percent")} style={{ width: 70 }} /></label>
      )}
      </div>
      {form.kind === "code" && (
        <>
          <span className="field-label">Starter code (students see this)</span>
          <PythonEditor value={form.starter_code} height="140px" runnable
            placeholder="def add(a, b):\n    # your code here\n    pass"
            onChange={(v) => setForm((f) => ({ ...f, starter_code: v }))} />
          <span className="field-label">Hidden tests (pytest). Leave empty for no autograding.
            {" "}<button type="button" className="link small" onClick={() => setForm((f) => ({ ...f, test_code: SAMPLE_TESTS }))}>
              Insert example</button></span>
          <PythonEditor value={form.test_code} height="180px"
            placeholder="from solution import add\n\ndef test_add():\n    assert add(2, 3) == 5"
            onChange={(v) => setForm((f) => ({ ...f, test_code: v }))} />
        </>
      )}
      <div className="row">
        <button>Add assignment</button>
        {error && <p className="error">{error}</p>}
      </div>
    </form>
  );
}

function scoreText(s, max) {
  if (!s.grade) return null;
  const g = s.grade;
  const base = `${g.final_points}/${max}`;
  return g.penalty_percent ? `${base} (${g.points} − ${g.penalty_percent}% late)` : base;
}

function AutoStatus({ s }) {
  const ag = s.autograde;
  if (!ag) return null;
  if (ag.status === "pending" || ag.status === "running")
    return <div className="auto muted">⏳ Autograder running…</div>;
  if (ag.status === "error") return <div className="auto error">⚠ Autograder error</div>;
  return <div className="auto done">✔ {ag.passed}/{ag.total} tests passed · {ag.points} pts</div>;
}

function Assignment({ a, manage }) {
  const [subs, setSubs] = useState([]);
  const [file, setFile] = useState(null);
  const [code, setCode] = useState(a.starter_code || "");
  const [msg, setMsg] = useState("");
  const [viewing, setViewing] = useState(null);
  const load = () => api.submissions(a.id).then((list) => { setSubs(list); return list; })
    .catch((e) => { setMsg(e.message); return []; });

  useEffect(() => {
    // Students reopen their latest attempt in the editor.
    load().then((list) => {
      if (!manage && a.kind === "code" && list.length) {
        api.code(list[0].id).then((r) => setCode(r.code)).catch(() => {});
      }
    });
  }, [a.id]);

  // Poll while any submission is still being graded.
  const busy = subs.some((s) => s.autograde && ["pending", "running"].includes(s.autograde.status));
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [busy]);

  const submitCode = async () => {
    setMsg("");
    try {
      const s = await api.submitCode(a.id, code);
      setMsg(s.late ? "Submitted, but late" : "Submitted ✓");
      load();
    } catch (err) { setMsg(err.message); }
  };

  const regradeAll = async () => {
    try { const r = await api.regradeAll(a.id); setMsg(`${r.queued} submission(s) queued for regrading`); load(); }
    catch (err) { setMsg(err.message); }
  };

  const pastDue = a.due_at && new Date(a.due_at) < new Date();
  const closed = pastDue && !a.allow_late;

  const upload = async (e) => {
    e.preventDefault();
    if (!file) return;
    try {
      const s = await api.submit(a.id, file);
      setMsg(s.late ? "Submitted, but late" : "Submitted ✓");
      setFile(null);
      e.target.reset();
      load();
    } catch (err) { setMsg(err.message); }
  };

  return (
    <div className="card">
      <h3>{a.title} <span className="muted small">· {a.max_points} pts
        {a.due_at && ` · due ${new Date(a.due_at).toLocaleString()}`}
        {a.due_at && (a.allow_late
          ? a.late_penalty_percent > 0 && ` · late: −${a.late_penalty_percent}%`
          : " · no late work")}</span></h3>
      <p>{a.description}</p>

      {a.autograded && <p className="muted small">🧪 Autograded: your code is tested on the server when you submit.</p>}
      {manage && a.autograded && (
        <div className="row"><button className="secondary" onClick={regradeAll}>Regrade all</button></div>
      )}

      {!manage && a.kind === "code" && (closed ? <p className="muted">The deadline has passed. Submissions are closed.</p> : (
        <div className="stack">
          <PythonEditor value={code} onChange={setCode} runnable />
          <div className="row"><button onClick={submitCode} disabled={!code.trim()}>
            {pastDue ? "Submit late" : "Submit code"}</button></div>
        </div>
      ))}

      {!manage && a.kind !== "code" && (closed ? <p className="muted">The deadline has passed. Submissions are closed.</p> : (
        <form className="row" onSubmit={upload}>
          <input type="file" accept=".py,.ipynb,.pdf,.zip,.txt,.md,.png,.jpg"
            onChange={(e) => setFile(e.target.files[0])} />
          <button disabled={!file}>{pastDue ? "Submit late" : "Submit"}</button>
        </form>
      ))}
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
                <td><a href={api.fileUrl(s.id)}>{s.original_name}</a>
                  {a.kind === "code" && <> · <button className="link small" onClick={() => setViewing(s)}>view</button></>}</td>
                <td className="small">{new Date(s.submitted_at).toLocaleString()}
                  {s.late && <span className="badge-late">late</span>}</td>
                <td><AutoStatus s={s} />
                  {manage ? <GradeForm s={s} max={a.max_points} onSaved={load} />
                  : s.grade ? `${scoreText(s, a.max_points)} ${s.grade.feedback ? "· " + s.grade.feedback : ""}`
                  : !s.autograde && <span className="muted">Not graded</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {viewing && <SubmissionViewer s={viewing} manage={manage} onClose={() => setViewing(null)} onRegraded={load} />}
    </div>
  );
}

function SubmissionViewer({ s, manage, onClose, onRegraded }) {
  const [code, setCode] = useState("Loading…");
  const [err, setErr] = useState("");
  useEffect(() => { api.code(s.id).then((r) => setCode(r.code)).catch((e) => setCode(e.message)); }, [s.id]);
  const regrade = async () => {
    try { await api.regrade(s.id); onRegraded(); onClose(); } catch (e) { setErr(e.message); }
  };
  return (
    <dialog open aria-label="Submission">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{s.student} · {new Date(s.submitted_at).toLocaleString()}</h3>
        <button className="secondary" onClick={onClose}>Close</button>
      </div>
      <PythonEditor value={code} readOnly runnable={manage} height="300px" />
      {manage && s.autograde?.log && (<><h4>Autograder output</h4><pre className="log">{s.autograde.log}</pre></>)}
      {manage && s.autograde && <button className="secondary" onClick={regrade}>Regrade</button>}
      {err && <p className="error">{err}</p>}
    </dialog>
  );
}

function GradeForm({ s, max, onSaved }) {
  const [points, setPoints] = useState(s.grade?.points ?? s.autograde?.points ?? "");
  useEffect(() => {
    if (!s.grade && s.autograde?.points != null) setPoints(s.autograde.points);
  }, [s.autograde?.points]);
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
        aria-label="Points" onChange={(e) => setPoints(e.target.value)} style={{ width: 70 }} />
      <input placeholder="Feedback" value={feedback} onChange={(e) => setFeedback(e.target.value)} />
      <button>{s.grade ? "Update" : "Save"}</button>
      {s.grade?.penalty_percent > 0 && <span className="small muted">→ {s.grade.final_points} after late penalty</span>}
      {err && <span className="error">{err}</span>}
    </form>
  );
}
