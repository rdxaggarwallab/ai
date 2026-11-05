import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../main";

const ROLES = ["student", "ta", "teacher", "admin"];

export default function Admin() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = () => api.users(q).then(setUsers).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [q]);

  const changeRole = async (u, role) => {
    setError(""); setMsg("");
    try {
      await api.updateUser(u.id, { role });
      setMsg(`${u.name} is now ${role}`);
      load();
    } catch (e) { setError(e.message); }
  };

  const resetPw = async (u) => {
    const pw = window.prompt(`New password for ${u.email} (min 8 characters):`);
    if (!pw) return;
    setError(""); setMsg("");
    try {
      await api.resetPassword(u.id, pw);
      setMsg(`Password reset for ${u.email}. Tell them the new password.`);
    } catch (e) { setError(e.message); }
  };

  return (
    <>
      <h1>Users</h1>
      <p className="muted">Change roles, make TAs and reset passwords. To add a TA to a course,
        give the person the TA role here, then add them from the course page.</p>
      <input placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} />
      {msg && <p className="ok">{msg}</p>}
      {error && <p className="error">{error}</p>}
      <table className="card">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th></th></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.name}</td>
              <td>{u.email}</td>
              <td>
                <select value={u.role} disabled={u.id === me.id} aria-label={`Role for ${u.email}`}
                  onChange={(e) => changeRole(u, e.target.value)}>
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </td>
              <td><button className="secondary" onClick={() => resetPw(u)}>Reset password</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
