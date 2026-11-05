import { useEffect, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";

const RUN_LIMIT_MS = 15000;

/** Code editor. With `runnable`, adds Run/Stop and an output panel (runs in the browser). */
export default function PythonEditor({ value, onChange, runnable = false, height = "260px",
  readOnly = false, placeholder }) {
  const workerRef = useRef(null);
  const timerRef = useRef(null);
  const [output, setOutput] = useState([]);
  const [status, setStatus] = useState("");
  const [running, setRunning] = useState(false);

  const newWorker = () => {
    const w = new Worker(new URL("../pyWorker.js", import.meta.url), { type: "module" });
    w.onmessage = (e) => {
      const m = e.data;
      if (m.type === "stdout") setOutput((o) => [...o, { kind: "out", text: m.text }]);
      else if (m.type === "stderr") setOutput((o) => [...o, { kind: "err", text: m.text }]);
      else if (m.type === "status") {
        setStatus(m.text);
        if (m.text === "") {
          // Python is loaded and the student's code is starting: now the time limit applies.
          clearTimeout(timerRef.current);
          timerRef.current = setTimeout(
            () => stop(`Stopped: ran longer than ${RUN_LIMIT_MS / 1000}s (infinite loop?)`), RUN_LIMIT_MS);
        }
      }
      else if (m.type === "done") {
        clearTimeout(timerRef.current);
        setRunning(false);
        setStatus("");
        if (m.error) setOutput((o) => [...o, { kind: "err", text: m.error }]);
      }
    };
    workerRef.current = w;
  };

  useEffect(() => () => { workerRef.current?.terminate(); clearTimeout(timerRef.current); }, []);

  const stop = (reason) => {
    workerRef.current?.terminate();
    workerRef.current = null; // next run starts a fresh worker
    clearTimeout(timerRef.current);
    setRunning(false);
    setStatus("");
    setOutput((o) => [...o, { kind: "err", text: reason }]);
  };

  const run = () => {
    if (!workerRef.current) newWorker();
    setOutput([]);
    setRunning(true);
    workerRef.current.postMessage({ id: Date.now(), code: value });
    // Safety net while Python loads; replaced by the real limit once code starts.
    timerRef.current = setTimeout(() => stop("Stopped: Python took too long to load."), 90000);
  };

  return (
    <div className="editor">
      <CodeMirror value={value} height={height} extensions={[python()]} readOnly={readOnly}
        placeholder={placeholder} onChange={onChange} basicSetup={{ tabSize: 4 }} />
      {runnable && (
        <>
          <div className="row" style={{ marginTop: 8 }}>
            {running
              ? <button type="button" className="secondary" onClick={() => stop("Stopped.")}>■ Stop</button>
              : <button type="button" className="secondary" onClick={run}>▶ Run</button>}
            {status && <span className="muted small">{status}</span>}
            <span className="muted small">Runs in your browser. Grading happens on the server when you submit.</span>
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
