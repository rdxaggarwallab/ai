"""Autograder attacks run in the real Docker sandbox (needs the lms-grader:latest image).

A wrong solution (add() returns 0, so 1 of 2 tests should pass) tries to get a better score.
"""
import shutil
import subprocess

import pytest

from conftest import client_for, join

TESTS = ("from solution import add\n\n"
         "def test_pos():\n    assert add(2, 3) == 5\n\n"
         "def test_zero():\n    assert add(-1, 1) == 0\n")


def docker_ok():
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "image", "inspect", "lms-grader:latest"],
                          capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not docker_ok(), reason="Docker + lms-grader image not available")

FORGE_ATEXIT = '''
import atexit
def _forge():
    open("/tmp/junit.xml", "w").write(
        '<testsuite tests="2" failures="0" errors="0" skipped="0"/>')
atexit.register(_forge)
def add(a, b):
    return 0
'''

FORGE_NEGATIVE = '''
import atexit
atexit.register(lambda: open("/tmp/junit.xml", "w").write(
    '<testsuite tests="2" failures="-8" errors="0" skipped="0"/>'))
def add(a, b):
    return 0
'''

# Covert channel: the student chooses the numbers shown to them, so they can read the hidden
# tests from disk and leak them a few bytes at a time through "passed/total".
LEAK = '''
import atexit
_secret = open("test_solution.py", "rb").read()[:6]
_n = int.from_bytes(_secret, "big")
atexit.register(lambda: open("/tmp/junit.xml", "w").write(
    f'<testsuite tests="{_n}" failures="0" errors="0" skipped="0"/>'))
def add(a, b):
    return 0
'''

MONKEYPATCH = '''
import _pytest.python
_orig = _pytest.python.Function.runtest
def _always_pass(self):
    try:
        _orig(self)
    except AssertionError:
        pass
_pytest.python.Function.runtest = _always_pass
def add(a, b):
    return 0
'''


@pytest.fixture
def code_assignment(app):
    app.config.update(AUTOGRADER="docker", GRADE_INLINE=True, GRADER_TIMEOUT=20)
    t = client_for(app, "t@x.com", "teacher")
    cid = t.post("/api/courses", json={"code": "C1", "title": "x"}).json["id"]
    aid = t.post(f"/api/courses/{cid}/assignments", json={
        "title": "add", "kind": "code", "max_points": 10, "test_code": TESTS}).json["id"]
    s = client_for(app, "s@x.com")
    join(s, cid)
    return s, aid


def submit(s, aid, code):
    r = s.post(f"/api/assignments/{aid}/submissions", json={"code": code})
    assert r.status_code == 201, r.json
    return r.json["autograde"]


def test_guard_honest_wrong_solution_scores_half(code_assignment):
    s, aid = code_assignment
    ag = submit(s, aid, "def add(a, b):\n    return 0\n")
    assert (ag["status"], ag["passed"], ag["total"], ag["points"]) == ("done", 1, 2, 5.0)


def test_guard_unicode_solution(code_assignment):
    s, aid = code_assignment
    ag = submit(s, aid, "# नमस्ते 🤖\ndef add(a, b):\n    print('résumé ✓')\n    return a + b\n")
    assert (ag["status"], ag["passed"], ag["total"]) == ("done", 2, 2)


@pytest.mark.parametrize("code", [FORGE_ATEXIT, MONKEYPATCH], ids=["atexit-junit", "monkeypatch-pytest"])
def test_bug_wrong_solution_forges_full_score(code_assignment, code):
    s, aid = code_assignment
    ag = submit(s, aid, code)
    assert ag["points"] in (None, 5.0), f"wrong solution scored {ag['passed']}/{ag['total']} = {ag['points']} pts"


def test_bug_forged_score_above_max_points(code_assignment):
    s, aid = code_assignment
    ag = submit(s, aid, FORGE_NEGATIVE)
    assert ag["points"] is None or ag["points"] <= 10, \
        f"{ag['passed']}/{ag['total']} tests = {ag['points']} pts out of 10"


def test_bug_hidden_tests_leak_through_score(code_assignment):
    s, aid = code_assignment
    ag = submit(s, aid, LEAK)
    leaked = (ag["total"] or 0).to_bytes(6, "big") if ag["total"] else b""
    assert leaked != TESTS.encode()[:6], f"student read {leaked!r} of the hidden tests"


def test_guard_huge_output_is_capped(code_assignment, app):
    s, aid = code_assignment
    ag = submit(s, aid, "print('x' * 50_000_000)\ndef add(a, b):\n    return a + b\n")
    assert ag["status"] in ("done", "error")
    from app.models import Submission
    from app.extensions import db
    log = db.session.query(Submission).order_by(Submission.id.desc()).first().grading_log
    assert len(log) <= 21_000
