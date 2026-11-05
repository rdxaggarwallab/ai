// Runs student Python in the browser with Pyodide, inside a Web Worker so a
// runaway loop can't freeze the page (the page can terminate this worker).
// This only runs code on the student's own computer; grading happens on the server.

const CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const LOCAL = new URL("/pyodide/", self.location.origin).href;

let pyodidePromise = null;
let source = null; // "cdn" (all packages available) or "local" (core Python only)

async function cdnReachable() {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 4000);
    const r = await fetch(CDN + "pyodide-lock.json", { method: "HEAD", signal: ctrl.signal });
    clearTimeout(t);
    return r.ok;
  } catch {
    return false;
  }
}

async function load() {
  const { loadPyodide } = await import(/* @vite-ignore */ LOCAL + "pyodide.mjs");
  // CDN: full package set (numpy, ...). Local copy: core Python only, but always works.
  if (await cdnReachable()) {
    try {
      const py = await loadPyodide({ indexURL: CDN });
      source = "cdn";
      return py;
    } catch {
      /* fall through to the local copy */
    }
  }
  const py = await loadPyodide({ indexURL: LOCAL });
  source = "local";
  return py;
}

self.onmessage = async (e) => {
  const { id, code } = e.data;
  const send = (msg) => self.postMessage({ id, ...msg });
  try {
    if (!pyodidePromise) {
      send({ type: "status", text: "Loading Python (first run takes a few seconds)…" });
      pyodidePromise = load();
    }
    const py = await pyodidePromise;
    py.setStdout({ batched: (text) => send({ type: "stdout", text }) });
    py.setStderr({ batched: (text) => send({ type: "stderr", text }) });
    if (source === "cdn") {
      await py.loadPackagesFromImports(code);
    }
    send({ type: "status", text: "" });
    // Fresh globals each run so old variables don't leak between runs.
    const globals = py.toPy({});
    try {
      await py.runPythonAsync(code, { globals });
    } finally {
      globals.destroy();
    }
    send({ type: "done" });
  } catch (err) {
    let msg = String(err.message || err);
    if (/No module named/.test(msg) && source === "local") {
      msg += "\n(Offline mode: only the Python standard library is available. "
        + "Libraries like numpy need internet access.)";
    }
    send({ type: "done", error: msg });
  }
};
