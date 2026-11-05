// All calls go to /api (proxied to Flask). The login token lives in an
// httpOnly cookie; we only echo the CSRF cookie back as a header.
function csrfToken() {
  const m = document.cookie.match(/(?:^|; )csrf_access_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function request(method, path, body) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (method !== "GET") opts.headers["X-CSRF-TOKEN"] = csrfToken();
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, opts);
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new Error(data?.error || data?.msg || `Request failed (${res.status})`);
  return data;
}

export const api = {
  me: () => request("GET", "/auth/me"),
  login: (email, password) => request("POST", "/auth/login", { email, password }),
  register: (form) => request("POST", "/auth/register", form),
  logout: () => request("POST", "/auth/logout"),

  courses: () => request("GET", "/courses"),
  course: (id) => request("GET", `/courses/${id}`),
  createCourse: (form) => request("POST", "/courses", form),
  enroll: (id) => request("POST", `/courses/${id}/enroll`),

  assignments: (courseId) => request("GET", `/courses/${courseId}/assignments`),
  createAssignment: (courseId, form) => request("POST", `/courses/${courseId}/assignments`, form),
  submissions: (assignmentId) => request("GET", `/assignments/${assignmentId}/submissions`),
  submit: (assignmentId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request("POST", `/assignments/${assignmentId}/submissions`, fd);
  },
  grade: (submissionId, points, feedback) =>
    request("PUT", `/submissions/${submissionId}/grade`, { points, feedback }),
  fileUrl: (submissionId) => `/api/submissions/${submissionId}/file`,

  myGrades: () => request("GET", "/grades"),

  // admin
  users: (q = "") => request("GET", `/admin/users${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  updateUser: (id, changes) => request("PATCH", `/admin/users/${id}`, changes),
  resetPassword: (id, password) => request("POST", `/admin/users/${id}/password`, { password }),

  // course TAs
  staff: (courseId) => request("GET", `/courses/${courseId}/staff`),
  addStaff: (courseId, email) => request("POST", `/courses/${courseId}/staff`, { email }),
  removeStaff: (courseId, userId) => request("DELETE", `/courses/${courseId}/staff/${userId}`),
};
