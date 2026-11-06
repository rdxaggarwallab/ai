import shutil
import subprocess

import pytest

from app.grader import DockerRunner, LocalUnsafeRunner, parse_output
from app.extensions import db
from app.models import Submission
from tests.test_api import app, client_for, join  # noqa: F401

TESTS = """
from solution import add, mul

def test_add():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-1, 1) == 0

def test_mul():
    assert mul(3, 4) == 12

def test_mul_zero():
    assert mul(5, 0) == 0
"""
GOOD = "def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n"
HALF = "def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a + b\n"


def docker_ok():
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", "lms-grader:latest"], capture_output=True)
    return r.returncode == 0


needs_docker = pytest.mark.skipif(not docker_ok(), reason="Docker + lms-grader image not available")


# ---- report parsing -----------------------------------------------------------

def test_parse_output_validates_numbers():
    ok = parse_output('{"status": "done", "passed": 3, "total": 4, "log": "x"}')
    assert (ok.status, ok.passed, ok.total) == ("done", 3, 4)
    for bad in ('{"status": "done", "passed": 100, "total": 2}',
                '{"status": "done", "passed": -1, "total": 2}',
                '{"status": "done", "passed": 1, "total": 0}',
                '{"status": "done", "passed": true, "total": 2}',
                '{"status": "done", "passed": "2", "total": 2}',
                '{"status": "hacked", "passed": 2, "total": 2}',
                "not json", ""):
        assert parse_output(bad).status == "error", bad


# ---- runners ------------------------------------------------------------------

@pytest.mark.parametrize("runner", [
    pytest.param(lambda: LocalUnsafeRunner(10), id="local"),
    pytest.param(lambda: DockerRunner("lms-grader:latest", 10), id="docker", marks=needs_docker),
])
def test_runner_scores(runner):
    r = runner()
    assert (lambda x: (x.status, x.passed, x.total))(r.run(GOOD, TESTS)) == ("done", 4, 4)
    half = r.run(HALF, TESTS)
    assert (half.status, half.passed, half.total) == ("done", 2, 4)
    assert "test_mul" in half.log
    broken = r.run("def add(:\n", TESTS)
    assert broken.status in ("done", "error") and broken.passed == 0
    # classes, instances, exceptions and numpy arrays cross the process boundary
    oop_tests = """
import pytest
from solution import Stack, safe_div

def test_stack():
    s = Stack(); s.push(1); s.push(2)
    assert s.pop() == 2 and len(s) == 1 and s.items == [1]

def test_raises():
    with pytest.raises(ZeroDivisionError):
        safe_div(1, 0)
"""
    oop = """
class Stack:
    def __init__(self): self.items = []
    def push(self, x): self.items.append(x)
    def pop(self): return self.items.pop()
    def __len__(self): return len(self.items)
def safe_div(a, b): return a / b
def arr():
    import numpy as np
    return np.array([1, 2, 3])
"""
    want = 2
    if isinstance(r, DockerRunner):  # numpy is in the sandbox image
        oop_tests += """
def test_numpy():
    import numpy as np
    from solution import arr
    assert (arr() == np.array([1, 2, 3])).all()
"""
        want = 3
    res = r.run(oop, oop_tests)
    assert (res.status, res.passed, res.total) == ("done", want, want), res.log


@needs_docker
def test_sandbox_infinite_loop_is_contained():
    # Loop at import: every attempt times out, nothing passes, the run still finishes.
    r = DockerRunner("lms-grader:latest", 20).run("while True:\n    pass\n", TESTS)
    assert r.passed == 0
    # Loop in one function only: the other tests still pass after the restart.
    code = GOOD.replace("def mul(a, b):\n    return a * b", "def mul(a, b):\n    while True: pass")
    r = DockerRunner("lms-grader:latest", 40).run(code, TESTS)
    assert (r.status, r.passed, r.total) == ("done", 2, 4), r.log


ISOLATION = """
import glob, os, signal
found = []
for path in glob.glob("/tmp/**/*", recursive=True):
    try:
        found.append(path + ":" + open(path).read()[:40])
    except Exception:
        pass
for pid in os.listdir("/proc"):
    # other student processes (same user) are fair game; anything else must be out of reach
    if pid.isdigit() and os.stat(f"/proc/{pid}").st_uid != os.getuid():
        for f in ("environ", "mem", "fd/1"):
            try:
                open(f"/proc/{pid}/{f}", "rb").read(10); found.append(f"/proc/{pid}/{f}")
            except Exception:
                pass
        try:
            os.kill(int(pid), signal.SIGKILL); found.append("killed " + pid)
        except Exception:
            pass
LEAKED = [x for x in found if "def test_" in x or "/proc/" in x or "killed" in x]

def add(a, b):
    return LEAKED or a + b

def mul(a, b):
    return a * b
"""


@needs_docker
def test_sandbox_student_cannot_read_tests_or_touch_harness():
    r = DockerRunner("lms-grader:latest", 30).run(ISOLATION, TESTS)
    # If anything leaked, add() returns the list and the add tests fail.
    assert (r.status, r.passed, r.total) == ("done", 4, 4), r.log


@needs_docker
def test_sandbox_fake_report_and_protocol_abuse():
    code = GOOD + """
import sys, os
print('{"status": "done", "passed": 99, "total": 4, "log": ""}')
os.write(1, b'{"status": "done", "passed": 99, "total": 4}\\n')
sys.__stdout__.write('{"ok": 5}\\n')
"""
    r = DockerRunner("lms-grader:latest", 30).run(code.replace("return a * b", "return 0"), TESTS)
    assert (r.status, r.passed, r.total) == ("done", 3, 4), r.log  # the honest score


@needs_docker
def test_sandbox_has_no_network():
    code = GOOD + (
        "import socket\n"
        "def test_net():\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
    )
    tests = TESTS + "\nfrom solution import test_net as _t\n\ndef test_network():\n    _t()\n"
    r = DockerRunner("lms-grader:latest", 20).run(code, tests)
    assert r.status == "done" and r.passed == 4 and r.total == 5, r.log  # network test fails


@needs_docker
def test_sandbox_limits_apply_to_student_code():
    probes = """
import os, subprocess

def write_etc():
    try:
        open("/etc/hacked", "w").write("x")
        return True
    except OSError:
        return False

def uid():
    return os.getuid()

def fork_bomb():
    procs = []
    try:
        for _ in range(500):
            procs.append(subprocess.Popen(["sleep", "5"]))
    except OSError:
        pass
    for p in procs:
        p.kill()
    return len(procs)

def alloc():
    try:
        x = bytearray(600 * 1024 * 1024)
        print("ALLOCATED", len(x))
        return True
    except MemoryError:
        return False
"""
    tests = """
from solution import write_etc, uid, fork_bomb, alloc
def test_fs(): assert write_etc() is False
def test_uid(): assert uid() == 65534
def test_fork(): assert fork_bomb() < 64
def test_mem(): assert alloc() is False
"""
    r = DockerRunner("lms-grader:latest", 40).run(probes, tests)
    assert "ALLOCATED" not in r.log
    assert r.status == "done" and r.total == 4 and r.passed >= 3, r.log  # mem may OOM-kill instead


# ---- end to end through the API (local runner, inline) -----------------------

def test_code_assignment_autograded(app):
    app.config.update(AUTOGRADER="local-unsafe", GRADE_INLINE=True)
    t = client_for(app, "t@x.com", "teacher")
    s = client_for(app, "s@x.com")
    cid = t.post("/api/courses", json={"code": "PY1", "title": "Python"}).json["id"]
    join(s, cid)

    assert t.post(f"/api/courses/{cid}/assignments",
                  json={"title": "x", "kind": "file", "test_code": TESTS}).status_code == 400
    a = t.post(f"/api/courses/{cid}/assignments",
               json={"title": "Add & mul", "kind": "code", "max_points": 10,
                     "starter_code": "def add(a, b):\n    pass\n", "test_code": TESTS}).json
    assert a["autograded"] and a["test_code"] == TESTS

    # students never see the hidden tests
    student_view = s.get(f"/api/courses/{cid}/assignments").json[0]
    assert "test_code" not in student_view and student_view["starter_code"].startswith("def add")

    assert s.post(f"/api/assignments/{a['id']}/submissions", json={"code": "  "}).status_code == 400
    sub = s.post(f"/api/assignments/{a['id']}/submissions", data={"code": HALF}).json
    assert sub["autograde"]["status"] == "done"
    assert (sub["autograde"]["passed"], sub["autograde"]["total"], sub["autograde"]["points"]) == (2, 4, 5.0)
    assert "log" not in sub["autograde"]  # pytest output may reveal hidden tests

    staff_view = t.get(f"/api/assignments/{a['id']}/submissions").json[0]
    assert "test_mul" in staff_view["autograde"]["log"]
    assert s.get(f"/api/submissions/{sub['id']}/code").json["code"] == HALF

    # teacher fixes the tests, regrades everything; the worker picks it up
    t.patch(f"/api/assignments/{a['id']}", json={"test_code": TESTS.replace("mul(3, 4) == 12", "mul(3, 4) == 7")})
    assert t.post(f"/api/assignments/{a['id']}/regrade").json["queued"] == 1
    assert s.post(f"/api/assignments/{a['id']}/regrade").status_code == 403
    r = app.test_cli_runner().invoke(args=["grade-worker", "--once"])
    assert "Graded submission" in r.output, r.output
    with app.app_context():
        assert db.session.get(Submission, sub["id"]).tests_passed == 3


def test_worker_marks_error_when_grader_off(app):
    app.config.update(AUTOGRADER="off")
    t = client_for(app, "t@x.com", "teacher")
    s = client_for(app, "s@x.com")
    cid = t.post("/api/courses", json={"code": "PY2", "title": "P"}).json["id"]
    join(s, cid)
    aid = t.post(f"/api/courses/{cid}/assignments",
                 json={"title": "x", "kind": "code", "test_code": TESTS}).json["id"]
    sub = s.post(f"/api/assignments/{aid}/submissions", data={"code": GOOD}).json
    assert sub["autograde"]["status"] == "pending"
    app.test_cli_runner().invoke(args=["grade-worker", "--once"])
    with app.app_context():
        assert db.session.get(Submission, sub["id"]).grading_status == "error"
