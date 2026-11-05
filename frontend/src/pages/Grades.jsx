import { useEffect, useState } from "react";
import { api } from "../api";

export default function Grades() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => { api.myGrades().then(setRows).catch((e) => setError(e.message)); }, []);
  return (
    <>
      <h1>My grades</h1>
      {error && <p className="error">{error}</p>}
      {rows.length === 0 ? <p className="muted">No submissions yet.</p> : (
        <table className="card">
          <thead><tr><th>Assignment</th><th>File</th><th>Submitted</th><th>Grade</th><th>Feedback</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.assignment}</td>
                <td>{r.original_name}</td>
                <td className="small">{new Date(r.submitted_at).toLocaleString()}
                  {r.late && <span className="badge-late">late</span>}</td>
                <td>{r.grade ? (r.grade.penalty_percent
                  ? `${r.grade.final_points}/${r.max_points} (${r.grade.points} − ${r.grade.penalty_percent}% late)`
                  : `${r.grade.final_points}/${r.max_points}`)
                  : r.autograde?.status === "done"
                    ? <span>{r.autograde.points}/{r.max_points} <span className="muted small">(autograder: {r.autograde.passed}/{r.autograde.total} tests, teacher may adjust)</span></span>
                    : r.autograde?.status === "error" ? <span className="muted">Autograder error, teacher will check</span>
                    : r.autograde ? <span className="muted">Autograder running…</span>
                    : <span className="muted">Pending</span>}</td>
                <td>{r.grade?.feedback}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
