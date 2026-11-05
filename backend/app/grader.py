"""Autograder: runs a teacher's pytest tests against a student's solution.py.

Student code is untrusted. In real use it only runs inside the Docker sandbox
(DockerRunner): no network, read-only filesystem, memory/CPU/process limits,
non-root user, and a hard timeout. LocalUnsafeRunner exists only for tests and
development on a machine without Docker; production refuses to use it.

Known limit: tests and student code share one Python process, so a determined
student could tamper with pytest itself. Hidden tests stop casual cheating;
teachers should still look at the code (see docs/PLAN.md, Phase 3 similarity check).
"""
import io
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timedelta

import click
from flask import current_app

from .extensions import db
from .models import Submission, now

MAX_LOG = 20_000  # characters of pytest output kept per submission


@dataclass
class Result:
    status: str  # "done" or "error"
    passed: int = 0
    total: int = 0
    log: str = ""


def _script(marker: str, timeout: int) -> str:
    # Runs inside the sandbox. JUnit XML is printed after a random marker so the
    # student's own prints can't be confused with it.
    return (
        "cd /tmp/w && "
        f"timeout -s KILL {timeout} python -m pytest -q -p no:cacheprovider "
        "--junitxml=/tmp/junit.xml test_solution.py > /tmp/out.txt 2>&1; "
        "cat /tmp/out.txt | head -c 20000; "
        f"echo; echo '{marker}'; cat /tmp/junit.xml 2>/dev/null"
    )


def _files(solution: str, tests: str) -> dict[str, str]:
    return {"solution.py": solution, "test_solution.py": tests}


def parse_output(raw: str, marker: str) -> Result:
    if marker not in raw:
        return Result("error", log=raw[:MAX_LOG] or "Grader produced no output")
    log, _, xml = raw.rpartition(marker)
    log = log.strip()[:MAX_LOG]
    try:
        root = ET.fromstring(xml.strip())
    except ET.ParseError:
        # pytest never wrote a report: usually the time limit was hit.
        return Result("error", log=(log + "\n\nNo test report: time limit hit or the run crashed.").strip())
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    total = sum(int(s.get("tests", 0)) for s in suites)
    bad = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    if total == 0:
        return Result("error", log=(log + "\n\nNo tests were collected.").strip())
    return Result("done", passed=total - bad - skipped, total=total, log=log)


class DockerRunner:
    def __init__(self, image: str, timeout: int):
        self.image, self.timeout = image, timeout

    def run(self, solution: str, tests: str) -> Result:
        marker = "==LMS-REPORT-" + secrets.token_hex(16) + "=="
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for name, text in _files(solution, tests).items():
                data = text.encode()
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o444
                tar.addfile(info, io.BytesIO(data))
        cmd = [
            "docker", "run", "--rm", "-i",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=64m,exec",
            "--memory", "256m", "--memory-swap", "256m",
            "--cpus", "1",
            "--pids-limit", "64",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "65534:65534",
            "--env", "HOME=/tmp",
            self.image,
            "sh", "-c", "mkdir /tmp/w && tar -x -C /tmp/w && " + _script(marker, self.timeout),
        ]
        try:
            p = subprocess.run(cmd, input=buf.getvalue(), capture_output=True,
                               timeout=self.timeout + 30)
        except subprocess.TimeoutExpired:
            return Result("error", log="Sandbox did not finish in time.")
        except FileNotFoundError:
            return Result("error", log="Docker is not installed on the grading server.")
        out = p.stdout.decode(errors="replace")
        if p.returncode != 0 and marker not in out:
            return Result("error", log=(out + p.stderr.decode(errors="replace"))[:MAX_LOG])
        return parse_output(out, marker)


class LocalUnsafeRunner:
    """DEVELOPMENT ONLY. Runs student code directly on this machine, with basic limits."""

    def __init__(self, timeout: int):
        self.timeout = timeout

    def run(self, solution: str, tests: str) -> Result:
        work = tempfile.mkdtemp(prefix="lms-grade-")
        try:
            for name, text in _files(solution, tests).items():
                with open(os.path.join(work, name), "w") as f:
                    f.write(text)
            junit = os.path.join(work, "junit.xml")

            def limits():  # Unix only; Windows has no rlimits (only the timeout applies)
                import resource

                resource.setrlimit(resource.RLIMIT_CPU, (self.timeout, self.timeout))
                resource.setrlimit(resource.RLIMIT_AS, (1024 * 2**20, 1024 * 2**20))

            try:
                p = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                     f"--junitxml={junit}", "test_solution.py"],
                    cwd=work, capture_output=True, timeout=self.timeout,
                    preexec_fn=None if os.name == "nt" else limits,
                    env={**({"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")} if os.name == "nt" else {}),
                         "PATH": os.environ.get("PATH", ""), "HOME": work},
                )
                log = (p.stdout + p.stderr).decode(errors="replace")
            except subprocess.TimeoutExpired:
                return Result("error", log=f"Time limit of {self.timeout}s exceeded.")
            marker = "==MARK=="
            xml = open(junit).read() if os.path.exists(junit) else ""
            return parse_output(log + marker + xml, marker)
        finally:
            shutil.rmtree(work, ignore_errors=True)


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
    """Run the tests for one submission and store the result."""
    a = sub.assignment
    runner = runner or get_runner()
    if runner is None:
        sub.grading_status, sub.grading_log = "error", "Autograder is turned off on this server."
    else:
        try:
            r = runner.run(read_solution(sub), a.test_code)
        except Exception as e:  # never let one bad submission kill the worker
            r = Result("error", log=f"Grader crashed: {e!r}")
        sub.grading_status, sub.grading_log = r.status, r.log
        sub.tests_passed, sub.tests_total = (r.passed, r.total) if r.status == "done" else (None, None)
        sub.auto_points = round(a.max_points * r.passed / r.total, 2) if r.status == "done" else None
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
        while True:
            sub = claim_next()
            if sub:
                grade_submission(sub)
                click.echo(f"Graded submission {sub.id}: {sub.grading_status} "
                           f"{sub.tests_passed}/{sub.tests_total}")
                continue
            if once:
                return
            time.sleep(2)


def sanitize_tests(text: str) -> str:
    return re.sub(r"\r\n?", "\n", text or "")
