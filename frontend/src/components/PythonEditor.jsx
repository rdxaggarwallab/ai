import { useEffect, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";

const RUN_LIMIT_MS = 15000;
const MAX_OUTPUT_CHARS = 100_000; // more than this and the program is stopped
const FLUSH_MS = 100; // output is shown in batches so a print() loop can't freeze the tab

function makeWorker() {
  const w = new Worker(new URL("../pyWorker.js", import.meta.url), { type: "module" });
  w.postMessage({ type: "preload" });
  return w;
}

/** Code editor. With `runnable`, adds Run/Stop and an output panel (runs in the browser). */
export default function PythonEditor({ value, onChange, runnable = false, height = "260px",
  readOnly = false, placeholder }) {
  const runningRef = useRef(null); // worker running the current program
  const spareRef = useRef(null); // warm worker for the next run
  const timerRef = useRef(null);
  const flushRef = useRef(null);
  const pendingRef = useRef([]);
  const sizeRef = useRef(0);
  const [output, setOutput] = useState([]);
  const [status, setStatus] = useState("");
  const [running, setRunning] = useState(false);

  useEffect(() => () => {
    runningRef.current?.terminate();
    spareRef.current?.terminate();
    clearTimeout(timerRef.current);
    clearTimeout(flushRef.current);
  }, []);

  const flush = () => {
    flushRef.current = null;
    const lines = pendingRef.current;
    pendingRef.current = [];
    if (lines.length) setOutput((o) => [...o, ...lines]);
  };

  const add = (kind, text) => {
    pendingRef.current.push({ kind, text });
    if (!flushRef.current) flushRef.current = setTimeout(flush, FLUSH_MS);
  };

  const finish = (message) => {
    runningRef.current?.terminate(); // a worker runs one program only
    runningRef.current = null;
    clearTimeout(timerRef.current);
    if (message) add("err", message);
    clearTimeout(flushRef.current);
    flush();
    setRunning(false);
    setStatus("");
  };

  const run = () => {
    const w = spareRef.current || makeWorker();
    spareRef.current = makeWorker(); // warm up the next one now
    runningRef.current = w;
    pendingRef.current = [];
    sizeRef.current = 0;
    setOutput([]);
    setRunning(true);
    w.onmessage = (e) => {
      if (runningRef.current !== w) return;
      const m = e.data;
      if (m.type === "stdout" || m.type === "stderr") {
        sizeRef.current += m.text.length + 1;
        if (sizeRef.current > MAX_OUTPUT_CHARS) {
          finish(`Stopped: too much output (over ${MAX_OUTPUT_CHARS / 1000} KB). Is print() inside an endless loop?`);
          return;
        }
        add(m.type === "stdout" ? "out" : "err", m.text);
      } else if (m.type === "status") {
        setStatus(m.text);
        if (m.text === "") {
          // Python is loaded and the code is starting: now the time limit applies.
          clearTimeout(timerRef.current);
          timerRef.current = setTimeout(
            () => finish(`Stopped: ran longer than ${RUN_LIMIT_MS / 1000}s (endless loop?)`), RUN_LIMIT_MS);
        }
      } else if (m.type === "done") {
        finish(m.error);
      }
    };
    w.postMessage({ type: "run", code: value });
    // Safety net while Python loads; replaced by the real limit once code starts.
    timerRef.current = setTimeout(() => finish("Stopped: Python took too long to load."), 90000);
  };

  return (
    <div className="editor">
      <CodeMirror value={value} height={height} extensions={[python()]} readOnly={readOnly}
        placeholder={placeholder} onChange={onChange} basicSetup={{ tabSize: 4 }} />
      {runnable && (
        <>
          <div className="row" style={{ marginTop: 8 }}>
            {running
              ? <button type="button" className="secondary" onClick={() => finish("Stopped.")}>■ Stop</button>
              : <button type="button" className="secondary" onClick={run}>▶ Run</button>}
            {status && <span className="muted small">{status}</span>}
            <span className="muted small">Runs in your browser, with no internet access. Grading happens on the server.</span>
          </div>
          {output.length > 0 && (
            <pre className="output" aria-label="Program output">
              {output.map((l, i) => <span key={i} className={l.kind === "err" ? "err" : ""}>{l.text + "\n"}</span>)}
            </pre>
          )}
        </>
      )}
    </div>
  );
}
