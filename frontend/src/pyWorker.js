// Runs Python in the browser with Pyodide, inside a Web Worker so a runaway loop can't
// freeze the page (the page terminates the worker).
//
// Security: the code may not be the viewer's own (a teacher pressing Run on a student's
// submission). Before any user code runs, this worker deletes every way to reach the
// network (fetch, XMLHttpRequest, WebSocket, ...), so the code can't call the LMS API
// with the viewer's login or send data anywhere. Each worker runs ONE program and is then
// thrown away; the page keeps a fresh one ready.

const CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const LOCAL = new URL("/pyodide/", self.location.origin).href;

let pyodidePromise = null;
let source = null; // "cdn" (all packages available) or "local" (core Python only)
let used = false;

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

const NETWORK_APIS = [
  "fetch", "XMLHttpRequest", "WebSocket", "WebSocketStream", "EventSource", "WebTransport",
  "importScripts", "Worker", "SharedWorker", "BroadcastChannel", "indexedDB", "caches",
  "Request", "Response", "Headers",
];

function cutNetwork() {
  for (let o = self; o; o = Object.getPrototypeOf(o)) {
    for (const name of NETWORK_APIS) {
      if (Object.prototype.hasOwnProperty.call(o, name)) {
        try { delete o[name]; } catch { /* ignore */ }
        try {
          Object.defineProperty(o, name, { value: undefined, writable: false, configurable: false });
        } catch { /* ignore */ }
      }
    }
  }
}

const SETUP = `
import builtins
def _no_input(prompt=""):
    raise RuntimeError(
        "input() doesn't work in the browser editor. "
        "Put example values in your code instead (e.g. name = 'Asha').")
builtins.input = _no_input
`;

self.onmessage = async (e) => {
  const { type, code } = e.data;
  const send = (msg) => self.postMessage(msg);
  if (!pyodidePromise) pyodidePromise = load();
  if (type === "preload") {
    try { await pyodidePromise; send({ type: "ready" }); } catch { /* reported on run */ }
    return;
  }
  if (used) {
    send({ type: "done", error: "Internal error: worker already used" });
    return;
  }
  used = true;
  try {
    send({ type: "status", text: "Loading Python…" });
    const py = await pyodidePromise;
    py.setStdout({ batched: (text) => send({ type: "stdout", text }) });
    py.setStderr({ batched: (text) => send({ type: "stderr", text }) });
    if (source === "cdn") {
      send({ type: "status", text: "Loading libraries…" });
      await py.loadPackagesFromImports(code);
    }
    cutNetwork(); // from here on, nothing can reach the network
    py.runPython(SETUP);
    send({ type: "status", text: "" }); // code starts now: the page starts its time limit
    await py.runPythonAsync(code);
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
