"""Autograder harness: runs a teacher's hidden pytest tests against a student's solution.py.

Trust model
-----------
The hidden tests and this harness are trusted. The student's code is not, so it never runs
in this process. It runs in a separate *student process*; when a test does
``from solution import add`` it gets a proxy, and ``add(2, 3)`` is sent to the student
process over a pipe. Only plain data comes back (JSON, never pickle), so nothing the
student sends can execute here.

In ``--sandbox`` mode (inside the Docker container, started as root with only the SETUID
and SETGID capabilities) the student processes run as uid 65534, then the harness drops to
uid 65533 before it writes the tests to disk. The student therefore cannot read the tests,
signal or trace the harness, or write the report: the report is this process's stdout.

``--local`` mode skips the user switch. It is for development and tests only.

Input: a tar on stdin with solution.py and test_solution.py.
Output: one JSON object on stdout: {"status", "passed", "total", "log"}.
"""
import argparse
import base64
import builtins
import contextlib
import io
import json
import math
import os
import queue
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import types

STUDENT_UID = 65534
HARNESS_UID = 65533
MAX_LINE = 4 * 1024 * 1024  # largest single RPC message accepted from a student process
MAX_STUDENT_LOG = 8_000  # characters of student prints kept in the log
MAX_LOG = 20_000
SPARES = 3  # extra student processes, used after one hangs or crashes
CALL_LIMIT = 10.0  # seconds for any single call into student code

# --------------------------------------------------------------------------------------
# Code that runs inside the student process. Kept small; it is the student's own process,
# so nothing here needs to be trusted.
# --------------------------------------------------------------------------------------
STUDENT_RUNNER = r'''
import base64, json, math, os, sys, tempfile, traceback

rpc_in = sys.stdin
rpc_out = os.fdopen(os.dup(1), "w", encoding="utf-8")
os.dup2(2, 1)                       # prints (even from C code) go to the log pipe
sys.stdout = sys.stderr

objects = {}
next_id = [1]

def enc(o, depth=0):
    if depth > 50:
        raise ValueError("value nested too deeply")
    if o is None or isinstance(o, (bool, str)):
        return o
    if isinstance(o, int):
        return o if abs(o) < 2**53 else {"__i": str(o)}
    if isinstance(o, float):
        return o if math.isfinite(o) else {"__f": repr(o)}
    if isinstance(o, complex):
        return {"__c": [enc(o.real), enc(o.imag)]}
    if isinstance(o, list):
        return [enc(x, depth + 1) for x in o]
    if isinstance(o, tuple):
        return {"__t": [enc(x, depth + 1) for x in o]}
    if isinstance(o, (set, frozenset)):
        return {"__s": [enc(x, depth + 1) for x in o]}
    if isinstance(o, dict):
        return {"__d": [[enc(k, depth + 1), enc(v, depth + 1)] for k, v in o.items()]}
    if isinstance(o, (bytes, bytearray)):
        return {"__b": base64.b64encode(bytes(o)).decode()}
    mod = type(o).__module__
    if mod == "numpy" and hasattr(o, "item") and getattr(o, "shape", None) == ():
        return enc(o.item(), depth + 1)
    if mod == "numpy" and type(o).__name__ == "ndarray":
        return {"__nd": enc(o.tolist(), depth + 1), "dtype": str(o.dtype)}
    oid = next_id[0]; next_id[0] += 1
    objects[oid] = o
    try:
        r = repr(o)[:200]
    except Exception:
        r = "<unrepresentable>"
    return {"__r": oid, "type": type(o).__name__, "repr": r}

def dec(o):
    if isinstance(o, list):
        return [dec(x) for x in o]
    if isinstance(o, dict):
        if "__r" in o: return objects[o["__r"]]
        if "__t" in o: return tuple(dec(x) for x in o["__t"])
        if "__s" in o: return set(dec(x) for x in o["__s"])
        if "__d" in o: return {dec(k): dec(v) for k, v in o["__d"]}
        if "__f" in o: return float(o["__f"])
        if "__i" in o: return int(o["__i"])
        if "__c" in o: return complex(dec(o["__c"][0]), dec(o["__c"][1]))
        if "__b" in o: return base64.b64decode(o["__b"])
        if "__nd" in o:
            import numpy
            return numpy.array(dec(o["__nd"]), dtype=o["dtype"])
    return o

def reply(msg):
    rpc_out.write(json.dumps(msg) + "\n")
    rpc_out.flush()

def handle(m):
    op = m["op"]
    if op == "load":
        work = tempfile.mkdtemp(prefix="student-")
        with open(os.path.join(work, "solution.py"), "w", encoding="utf-8") as f:
            f.write(m["source"])
        os.chdir(work)
        sys.path.insert(0, work)
        import solution
        objects[0] = solution
        return None
    t = objects[m["target"]]
    if op == "getattr": return getattr(t, m["name"])
    if op == "setattr": setattr(t, m["name"], dec(m["value"])); return None
    if op == "call": return t(*dec(m["args"]), **dec(m["kwargs"]))
    if op == "getitem": return t[dec(m["key"])]
    if op == "setitem": t[dec(m["key"])] = dec(m["value"]); return None
    if op == "len": return len(t)
    if op == "list": return list(t)
    if op == "str": return str(t)
    if op == "repr": return repr(t)
    if op == "bool": return bool(t)
    if op == "contains": return dec(m["item"]) in t
    if op == "eq": return t == dec(m["other"])
    if op == "lt": return t < dec(m["other"])
    if op == "hash": return hash(t)
    raise ValueError("unknown op " + str(op))

for line in rpc_in:
    try:
        m = json.loads(line)
        result = handle(m)
        reply({"ok": enc(result)})
    except BaseException as e:  # report everything, incl. SystemExit from student code
        if isinstance(e, KeyboardInterrupt):
            raise
        frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename != "<string>"]
        tb = "".join(traceback.format_list(frames)) + "".join(traceback.format_exception_only(e))
        reply({"err": [type(e).__name__, str(e)[:2000], tb[-3000:]]})
'''


# --------------------------------------------------------------------------------------
# Harness side
# --------------------------------------------------------------------------------------
class StudentCodeError(Exception):
    """An exception raised inside the student's code that has no builtin equivalent."""


class StudentCrashed(Exception):
    """The student's code hung, crashed or broke the protocol."""


_SAFE_DTYPE = set("abcdefghijklmnopqrstuvwxyz0123456789<>|")


class StudentProcess:
    def __init__(self, sandbox: bool):
        kw = {}
        if sandbox:
            kw = {"user": STUDENT_UID, "group": STUDENT_UID, "extra_groups": []}
        env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
               "HOME": tempfile.gettempdir()}
        if os.name == "nt":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        self.p = subprocess.Popen(
            [sys.executable, "-I", "-c", STUDENT_RUNNER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, cwd=tempfile.gettempdir(), **kw)
        self.replies: queue.Queue = queue.Queue()
        threading.Thread(target=self._read_replies, daemon=True).start()
        self.log = io.StringIO()
        threading.Thread(target=self._read_log, daemon=True).start()
        self.dead = False

    def _read_replies(self):
        while True:
            line = self.p.stdout.readline(MAX_LINE + 1)
            if not line:
                self.replies.put(None)
                return
            if len(line) > MAX_LINE:
                self.replies.put({"err": ["ValueError", "Return value too large", ""]})
                self.p.kill()
                return
            self.replies.put(line)

    def _read_log(self):
        total = 0
        while True:
            chunk = self.p.stderr.read(4096)
            if not chunk:
                return
            if total < MAX_STUDENT_LOG:
                self.log.write(chunk[: MAX_STUDENT_LOG - total].decode("utf-8", "replace"))
            total += len(chunk)  # keep draining so the student never blocks on output

    def request(self, msg: dict, timeout: float):
        if self.dead:
            raise StudentCrashed("student code stopped earlier")
        try:
            self.p.stdin.write((json.dumps(msg) + "\n").encode())
            self.p.stdin.flush()
            line = self.replies.get(timeout=timeout)
        except queue.Empty:
            self.kill()
            raise StudentCrashed(f"time limit: student code ran longer than {timeout:.0f}s") from None
        except (BrokenPipeError, OSError):
            self.kill()
            raise StudentCrashed("student code exited") from None
        if line is None:
            self.kill()
            raise StudentCrashed("student code exited or crashed")
        try:
            reply = json.loads(line) if isinstance(line, (bytes, str)) else line
        except ValueError:
            self.kill()
            raise StudentCrashed("student code broke the grading protocol") from None
        if not isinstance(reply, dict):
            raise StudentCrashed("student code broke the grading protocol")
        return reply

    def kill(self):
        self.dead = True
        try:
            self.p.kill()
        except OSError:
            pass


class Session:
    """The student's solution, loaded in a student process; replaced after a crash."""

    def __init__(self, procs, source):
        self.procs, self.source = procs, source
        self.current = None
        self.used = []
        self.generation = 0
        self.deadline = None

    def _proc(self):
        if self.current is None or self.current.dead:
            if not self.procs:
                raise StudentCrashed("student code crashed too many times")
            self.current = self.procs.pop(0)
            self.used.append(self.current)
            self.generation += 1
            self._call({"op": "load", "source": self.source})
        return self.current

    def _call(self, msg):
        remaining = self.deadline - time.monotonic() if self.deadline else CALL_LIMIT
        if remaining <= 0:
            raise StudentCrashed("overall time limit reached")
        reply = self.current.request(msg, min(CALL_LIMIT, remaining))
        if "err" in reply:
            name, text, tb = (list(reply["err"]) + ["", "", ""])[:3]
            exc = getattr(builtins, str(name), None)
            if isinstance(exc, type) and issubclass(exc, Exception) and exc is not StopIteration:
                err = exc(text)
            else:
                err = StudentCodeError(f"{name}: {text}")
            err.__notes__ = ["Traceback from the student's code:\n" + str(tb)]
            raise err
        return self.decode(reply.get("ok"), path=msg.get("_path"))

    def call(self, msg, remote=None):
        self._proc()  # (re)starts and loads the solution if needed
        if remote is not None and remote._gen != self.generation:
            # The process this object lived in was replaced. Names taken from the module
            # (functions, classes) are looked up again; other objects are gone.
            if remote._path is None:
                raise StudentCrashed("this object was lost when the student code restarted")
            fresh = self.resolve(remote._path)
            object.__setattr__(remote, "_id", fresh._id)
            object.__setattr__(remote, "_gen", fresh._gen)
            msg = {**msg, "target": remote._id}
        return self._call(msg)

    def resolve(self, path):
        obj = self.call({"op": "getattr", "target": 0, "name": path[0]})
        for name in path[1:]:
            obj = obj._op("getattr", name=name)
        return obj

    def decode(self, o, depth=0, path=None):
        if depth > 60:
            raise StudentCrashed("value nested too deeply")
        if o is None or isinstance(o, (bool, str)):
            return o
        if isinstance(o, (int, float)):
            return o
        if isinstance(o, list):
            return [self.decode(x, depth + 1) for x in o]
        if isinstance(o, dict):
            if "__t" in o:
                return tuple(self.decode(x, depth + 1) for x in o["__t"])
            if "__s" in o:
                return set(self.decode(x, depth + 1) for x in o["__s"])
            if "__d" in o:
                return {self.decode(k, depth + 1): self.decode(v, depth + 1) for k, v in o["__d"]}
            if "__f" in o:
                return float(str(o["__f"]))
            if "__i" in o:
                return int(str(o["__i"])[:5000])
            if "__c" in o:
                return complex(self.decode(o["__c"][0]), self.decode(o["__c"][1]))
            if "__b" in o:
                return base64.b64decode(str(o["__b"]))
            if "__nd" in o:
                data = self.decode(o["__nd"], depth + 1)
                dtype = str(o.get("dtype", ""))
                try:
                    import numpy
                except ImportError:
                    return data
                return numpy.array(data, dtype=dtype if set(dtype) <= _SAFE_DTYPE and dtype else None)
            if "__r" in o:
                return Remote(self, int(o["__r"]), str(o.get("type", "object"))[:80],
                              str(o.get("repr", ""))[:200], self.generation, path)
        raise StudentCrashed("student code sent an unknown value")

    def encode(self, o):
        if isinstance(o, Remote):
            return {"__r": o._id}
        if o is None or isinstance(o, (bool, str)):
            return o
        if isinstance(o, int):
            return o if abs(o) < 2**53 else {"__i": str(o)}
        if isinstance(o, float):
            return o if math.isfinite(o) else {"__f": repr(o)}
        if isinstance(o, complex):
            return {"__c": [self.encode(o.real), self.encode(o.imag)]}
        if isinstance(o, list):
            return [self.encode(x) for x in o]
        if isinstance(o, tuple):
            return {"__t": [self.encode(x) for x in o]}
        if isinstance(o, (set, frozenset)):
            return {"__s": [self.encode(x) for x in o]}
        if isinstance(o, dict):
            return {"__d": [[self.encode(k), self.encode(v)] for k, v in o.items()]}
        if isinstance(o, (bytes, bytearray)):
            return {"__b": base64.b64encode(bytes(o)).decode()}
        if type(o).__module__ == "numpy":
            if getattr(o, "shape", None) == ():
                return self.encode(o.item())
            if type(o).__name__ == "ndarray":
                return {"__nd": self.encode(o.tolist()), "dtype": str(o.dtype)}
        raise TypeError(f"can't send a {type(o).__name__} to the student's code")


class Remote:
    """Stand-in for an object that lives in the student process (a function, class, instance...)."""

    __slots__ = ("_s", "_id", "_type", "_repr", "_gen", "_path")

    def __init__(self, session, oid, typ, rep, gen, path=None):
        object.__setattr__(self, "_s", session)
        object.__setattr__(self, "_id", oid)
        object.__setattr__(self, "_type", typ)
        object.__setattr__(self, "_repr", rep)
        object.__setattr__(self, "_gen", gen)
        object.__setattr__(self, "_path", path)  # attribute names from the module, if known

    def _op(self, op, **kw):
        return self._s.call({"op": op, "target": self._id, **kw}, remote=self)

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        sub = None if self._path is None or self._type not in ("type", "module") else self._path + (name,)
        return self._op("getattr", name=name, _path=sub)

    def __setattr__(self, name, value):
        self._op("setattr", name=name, value=self._s.encode(value))

    def __call__(self, *args, **kwargs):
        return self._op("call", args=self._s.encode(list(args)), kwargs=self._s.encode(kwargs))

    def __getitem__(self, key):
        return self._op("getitem", key=self._s.encode(key))

    def __setitem__(self, key, value):
        self._op("setitem", key=self._s.encode(key), value=self._s.encode(value))

    def __len__(self):
        return self._op("len")

    def __iter__(self):
        return iter(self._op("list"))

    def __contains__(self, item):
        return self._op("contains", item=self._s.encode(item))

    def __eq__(self, other):
        return self._op("eq", other=self._s.encode(other))

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        return self._op("lt", other=self._s.encode(other))

    def __hash__(self):
        return self._op("hash")

    def __bool__(self):
        return self._op("bool")

    def __str__(self):
        return self._op("str")

    def __repr__(self):
        return f"<student {self._type}: {self._repr}>"


class SolutionModule(types.ModuleType):
    """``import solution`` in the tests gives this; attributes are fetched from the student process."""

    def __init__(self, session):
        super().__init__("solution")
        self.__dict__["_session"] = session

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        s = self.__dict__["_session"]
        return s.call({"op": "getattr", "target": 0, "name": name, "_path": (name,)})


class Collector:
    """pytest plugin: counts results here, in the trusted process."""

    def __init__(self):
        self.collected = 0
        self.failed = set()
        self.passed = set()
        self.collect_errors = 0

    def pytest_collection_modifyitems(self, items):
        self.collected = len(items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.collect_errors += 1

    def pytest_runtest_logreport(self, report):
        if report.failed or report.skipped:
            self.failed.add(report.nodeid)
        elif report.when == "call" and report.passed:
            self.passed.add(report.nodeid)


def read_input():
    data = sys.stdin.buffer.read()
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            if m.isfile() and m.name in ("solution.py", "test_solution.py") and m.size < 2_000_000:
                files[m.name] = tar.extractfile(m).read().decode("utf-8", "replace")
    return files.get("solution.py", ""), files.get("test_solution.py", "")


def drop_privileges():
    os.setgroups([])
    os.setgid(HARNESS_UID)
    os.setuid(HARNESS_UID)
    if os.getuid() != HARNESS_UID:
        raise RuntimeError("could not drop privileges")


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sandbox", action="store_true")
    mode.add_argument("--local", action="store_true")
    ap.add_argument("--timeout", type=float, default=25.0)
    args = ap.parse_args()
    started = time.monotonic()

    solution_src, tests_src = read_input()

    # Start the student processes first: switching their user needs our root rights,
    # which are dropped right after.
    procs = [StudentProcess(args.sandbox) for _ in range(1 + SPARES)]
    if args.sandbox:
        drop_privileges()
        os.umask(0o077)

    test_dir = tempfile.mkdtemp(prefix="tests-")  # 0700, random name: unreadable to the student
    test_file = os.path.join(test_dir, "test_solution.py")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(tests_src)

    session = Session(procs, solution_src)
    session.deadline = started + args.timeout
    sys.modules["solution"] = SolutionModule(session)

    import pytest  # imported after the user switch; only trusted code runs from here on

    collector = Collector()
    out = io.StringIO()
    os.chdir(test_dir)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            pytest.main(["test_solution.py", "-q", "-p", "no:cacheprovider", "--tb=short",
                         "-o", "console_output_style=classic", "--rootdir", test_dir,
                         "-W", "ignore::pytest.PytestAssertRewriteWarning"],
                        plugins=[collector])
        except BaseException as e:  # pragma: no cover - pytest itself failing
            out.write(f"\npytest crashed: {e!r}\n")

    for p in procs + session.used:
        p.kill()

    total = collector.collected
    passed = len(collector.passed - collector.failed)
    log = out.getvalue()
    time.sleep(0.05)  # let the log readers catch the last output
    student_out = "".join(p.log.getvalue() for p in session.used)
    if student_out.strip():
        log += "\n--- output printed by the student's code ---\n" + student_out
    if collector.collect_errors or total == 0:
        status = "error"
        log += "\nNo tests could be run (check the test file for errors)."
        passed = 0
    else:
        status = "done"
    result = {"status": status, "passed": passed, "total": total, "log": log[-MAX_LOG:]}
    sys.__stdout__.write(json.dumps(result) + "\n")
    sys.__stdout__.flush()
    os._exit(0)  # don't wait for reader threads of killed student processes


if __name__ == "__main__":
    main()
