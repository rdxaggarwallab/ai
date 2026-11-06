"""Autograder: runs a teacher's hidden pytest tests against a student's solution.py.

The work happens in ``grader/harness.py``. The hidden tests run in a trusted process, and
the student's code runs in a *separate* process under another user account, reached
only through a pipe that carries plain data. So student code cannot read the tests,
tamper with pytest, or write the score report (see the harness docstring).

DockerRunner: the harness runs inside a throwaway container: no network, read-only
filesystem, memory/CPU/process limits, all capabilities dropped except the two needed to
switch users, and a hard timeout. This is the only mode for real use.

LocalUnsafeRunner: runs the same harness directly on this machine *without* the
container or the user switch. Development and tests only; production refuses it.
"""
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from datetime import timedelta

import click
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db
from .models import Submission, now

MAX_LOG = 20_000  # characters of grader output kept per submission
MAX_TESTS = 1000
HARNESS_PATH = os.environ.get(
    "GRADER_HARNESS",
    os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "grader", "harness.py")),
)


@dataclass
class Result:
    status: str  # "done" or "error"
    passed: int = 0
    total: int = 0
    log: str = ""


def _tar(solution: str, tests: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, text in (("solution.py", solution), ("test_solution.py", tests)):
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o444
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def parse_output(raw: str) -> Result:
    """Parse the harness report: one JSON object on its last line.

    Only the harness writes to this stream (student code has no access to it), but the
    numbers are still checked, so a bug can never produce an impossible score.
    """
    lines = [ln for ln in raw.strip().splitlines() if ln.strip()]
    if not lines:
        return Result("error", log="Grader produced no output (time limit or crash).")
    try:
        r = json.loads(lines[-1])
        status, passed, total = r["status"], r["passed"], r["total"]
        log = str(r.get("log", ""))[-MAX_LOG:]
    except (ValueError, KeyError, TypeError):
        return Result("error", log=raw[-MAX_LOG:])
    if status not in ("done", "error"):
        return Result("error", log=log)
    if status == "error":
        return Result("error", log=log)
    if (not isinstance(passed, int) or not isinstance(total, int) or isinstance(passed, bool)
            or isinstance(total, bool) or not 0 < total <= MAX_TESTS or not 0 <= passed <= total):
        return Result("error", log=f"Grader returned an impossible score ({passed!r}/{total!r}).\n{log}")
    return Result("done", passed=passed, total=total, log=log)


class DockerRunner:
    def __init__(self, image: str, timeout: int):
        self.image, self.timeout = image, timeout

    def command(self):
        return [
            "docker", "run", "--rm", "-i",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=64m,exec,mode=1777",
            "--memory", "512m", "--memory-swap", "512m",
            "--cpus", "1",
            "--pids-limit", "64",
            # Starts as root with no powers except switching user; the harness drops to
            # uid 65533 and runs student code as uid 65534 straight away.
            "--user", "0:0",
            "--cap-drop", "ALL", "--cap-add", "SETUID", "--cap-add", "SETGID",
            "--security-opt", "no-new-privileges",
            "--env", "HOME=/tmp",
            self.image,
            "timeout", "-s", "KILL", str(self.timeout),
            "python", "-I", "/opt/grader/harness.py", "--sandbox", "--timeout", str(max(1, self.timeout - 3)),
        ]

    def run(self, solution: str, tests: str) -> Result:
        try:
            p = subprocess.run(self.command(), input=_tar(solution, tests), capture_output=True,
                               timeout=self.timeout + 30)
        except subprocess.TimeoutExpired:
            return Result("error", log="Sandbox did not finish in time.")
        except FileNotFoundError:
            return Result("error", log="Docker is not installed on the grading server.")
        out = p.stdout.decode("utf-8", errors="replace")
        if p.returncode != 0 and not out.strip():
            err = p.stderr.decode("utf-8", errors="replace")
            if p.returncode in (137, -9):
                err = f"Time limit of {self.timeout}s exceeded.\n" + err
            return Result("error", log=err[-MAX_LOG:])
        return parse_output(out)


class LocalUnsafeRunner:
    """DEVELOPMENT ONLY. Runs the harness on this machine with no container and no user switch."""

    def __init__(self, timeout: int):
        self.timeout = timeout

    def run(self, solution: str, tests: str) -> Result:
        if not os.path.exists(HARNESS_PATH):
            return Result("error", log=f"Grader harness not found at {HARNESS_PATH}")
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
        if os.name == "nt":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        try:
            p = subprocess.run(
                [sys.executable, "-I", HARNESS_PATH, "--local", "--timeout", str(max(1, self.timeout - 3))],
                input=_tar(solution, tests), capture_output=True, timeout=self.timeout + 10, env=env)
        except subprocess.TimeoutExpired:
            return Result("error", log=f"Time limit of {self.timeout}s exceeded.")
        out = p.stdout.decode("utf-8", errors="replace")
        if not out.strip():
            return Result("error", log=p.stderr.decode("utf-8", errors="replace")[-MAX_LOG:])
        return parse_output(out)


def get_runner():
    cfg = current_app.config
    mode = cfg["AUTOGRADER"]
    if mode == "docker":
        return DockerRunner(cfg["GRADER_IMAGE"], cfg["GRADER_TIMEOUT"])
    if mode == "local-unsafe":
        return LocalUnsafeRunner(cfg["GRADER_TIMEOUT"])
    return None


def read_solution(sub: Submission) -> str:
    with open(sub.file_path, encoding="utf-8", errors="replace") as f:
        return f.read()


def grade_submission(sub: Submission, runner=None) -> Submission:
    """Run the tests for one submission and store the result.

    If the submission was re-queued while the tests ran (a teacher pressed Regrade after
    fixing the tests), the now-outdated result is thrown away and the queued run stands.
    """
    a = sub.assignment
    started_status, started_at = sub.grading_status, sub.graded_started_at
    runner = runner or get_runner()
    if runner is None:
        r = Result("error", log="Autograder is turned off on this server.")
    else:
        try:
            r = runner.run(read_solution(sub), a.test_code)
        except Exception as e:  # never let one bad submission kill the worker
            r = Result("error", log=f"Grader crashed: {e!r}")
    db.session.refresh(sub)
    if sub.grading_status != started_status or sub.graded_started_at != started_at:
        return sub  # re-queued meanwhile: leave it for the next run
    sub.grading_status, sub.grading_log = r.status, r.log
    done = r.status == "done"
    sub.tests_passed, sub.tests_total = (r.passed, r.total) if done else (None, None)
    sub.auto_points = round(a.max_points * r.passed / r.total, 2) if done else None
    db.session.commit()
    return sub


def claim_next():
    """Atomically take one pending submission (safe with several workers on PostgreSQL)."""
    # Re-queue jobs stuck in "running" (worker crashed mid-run).
    stale = now() - timedelta(minutes=10)
    db.session.query(Submission).filter(
        Submission.grading_status == "running", Submission.graded_started_at < stale
    ).update({"grading_status": "pending"})
    q = (db.session.query(Submission).filter_by(grading_status="pending")
         .order_by(Submission.submitted_at))
    if db.engine.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    sub = q.first()
    if sub:
        sub.grading_status, sub.graded_started_at = "running", now()
    db.session.commit()
    return sub


def register_cli(app):
    @app.cli.command("grade-worker")
    @click.option("--once", is_flag=True, help="Grade everything pending, then exit.")
    def grade_worker(once):
        """Run the autograder worker: picks up pending submissions and grades them."""
        mode = current_app.config["AUTOGRADER"]
        click.echo(f"Grade worker started (mode: {mode})")
        if mode == "local-unsafe":
            click.echo("WARNING: local-unsafe runs student code WITHOUT a sandbox. Development only.")
        failures = 0
        while True:
            try:
                sub = claim_next()
                if sub:
                    grade_submission(sub)
                    click.echo(f"Graded submission {sub.id}: {sub.grading_status} "
                               f"{sub.tests_passed}/{sub.tests_total}")
                    failures = 0
                    continue
            except SQLAlchemyError as e:
                # Database restarted or connection dropped: keep the worker alive and retry.
                db.session.rollback()
                db.session.remove()
                failures += 1
                click.echo(f"Database error ({e.__class__.__name__}); retrying", err=True)
                time.sleep(min(30, 2 ** min(failures, 5)))
                continue
            if once:
                return
            time.sleep(2)


def sanitize_tests(text: str) -> str:
    return re.sub(r"\r\n?", "\n", text or "")
