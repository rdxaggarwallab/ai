import shutil
import subprocess

import pytest

from app.grader import DockerRunner, LocalUnsafeRunner, parse_output
from app.extensions import db
from app.models import Submission
from tests.test_api import app, client_for  # noqa: F401

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

def test_parse_output_counts_and_ignores_fake_marker():
    marker = "==M=="
    xml = '<testsuites><testsuite tests="4" failures="1" errors="0" skipped="0"/></testsuites>'
    r = parse_output("student printed ==FAKE==\n" + marker + xml, marker)
    assert (r.status, r.passed, r.total) == ("done", 3, 4)
    assert parse_output("no marker", marker).status == "error"
    assert parse_output("x" + marker + "not xml", marker).status == "error"


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


@needs_docker
def test_sandbox_infinite_loop_is_killed():
    r = DockerRunner("lms-grader:latest", 5).run("while True:\n    pass\n", TESTS)
    assert r.status == "error" and r.passed == 0


@needs_docker
def test_sandbox_has_no_network():
    code = GOOD + (
        "import socket\n"
        "def test_net():\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
    )
    tests = TESTS + "\nfrom solution import test_net as _t\n\ndef test_network():\n    _t()\n"
    r = DockerRunner("lms-grader:latest", 15).run(code, tests)
    assert r.status == "done" and r.passed == 4 and r.total == 5  # network test fails


@needs_docker
def test_sandbox_blocks_filesystem_and_fork_bomb_and_memory():
    tests = TESTS + '''
import os, subprocess
def test_cannot_write_outside_tmp():
    try:
        open("/etc/hacked", "w").write("x")
        assert False, "wrote to /etc"
    except OSError:
        pass

def test_not_root():
    assert os.getuid() == 65534

def test_fork_bomb_limited():
    procs = []
    try:
        for _ in range(500):
            procs.append(subprocess.Popen(["sleep", "5"]))
        assert False, "spawned 500 processes"
    except (OSError, BlockingIOError):
        pass
    finally:
        for p in procs:
            p.kill()

def test_memory_limited():
    try:
        x = bytearray(600 * 1024 * 1024)
        assert False, "allocated 600MB"
    except MemoryError:
        pass
'''
    r = DockerRunner("lms-grader:latest", 20).run(GOOD, tests)
    # memory test may also get the process OOM-killed -> error; either way nothing escaped
    if r.status == "done":
        assert r.passed == r.total == 8, r.log
    else:
        assert "allocated 600MB" not in r.log


# ---- end to end through the API (local runner, inline) -----------------------

def test_code_assignment_autograded(app):
    app.config.update(AUTOGRADER="local-unsafe", GRADE_INLINE=True)
    t = client_for(app, "t@x.com", "teacher")
    s = client_for(app, "s@x.com")
    cid = t.post("/api/courses", json={"code": "PY1", "title": "Python"}).json["id"]
    s.post(f"/api/courses/{cid}/enroll")

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
    s.post(f"/api/courses/{cid}/enroll")
    aid = t.post(f"/api/courses/{cid}/assignments",
                 json={"title": "x", "kind": "code", "test_code": TESTS}).json["id"]
    sub = s.post(f"/api/assignments/{aid}/submissions", data={"code": GOOD}).json
    assert sub["autograde"]["status"] == "pending"
    app.test_cli_runner().invoke(args=["grade-worker", "--once"])
    with app.app_context():
        assert db.session.get(Submission, sub["id"]).grading_status == "error"
