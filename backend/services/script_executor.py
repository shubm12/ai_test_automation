"""Stage 3 — execute a generated script and report a per-test-case result.

Uses pytest-json-report instead of scraping stdout, so status parsing is
structural rather than regex-based.

Two execution modes:
- run(script_id): headed + slowed down, for the user-facing /execute-tests
  call where watching the browser is the point.
- dry_run(file_path): headless + fast, used internally at generation time to
  verify a script actually works before it is returned to the caller.
"""
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

from schemas.execute import ExecuteResult


class ScriptExecutorService:
    """Holds the in-memory script_id -> file registry for this process.

    Intended to be used as a module-level singleton (see routers) so
    /generate-tests and /execute-tests share the same registry.
    """

    def __init__(self):
        self._registry: dict[str, dict] = {}

    def register(self, file_path: Path, title: str) -> str:
        script_id = str(uuid.uuid4())
        self._registry[script_id] = {"file_path": file_path, "title": title}
        return script_id

    def run(self, script_id: str) -> ExecuteResult:
        entry = self._registry.get(script_id)
        if entry is None:
            raise KeyError(f"Unknown script_id: {script_id}")

        file_path: Path = entry["file_path"]
        title: str = entry["title"]

        status, stdout, stderr = self._run_pytest(file_path, headed=True)
        return ExecuteResult(
            title=title,
            file=file_path.name,
            status=status,
            stdout=stdout,
            stderr=stderr,
        )

    def dry_run(self, file_path: Path) -> tuple[str, str | None]:
        """Headless verification pass. Returns (status, failure_detail)."""
        status, _, stderr = self._run_pytest(file_path, headed=False)
        return status, stderr

    @staticmethod
    def _run_pytest(file_path: Path, *, headed: bool) -> tuple[str, str, str | None]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "report.json"
            cmd = [
                "pytest",
                str(file_path),
                "-v",
                "--tb=short",
                "--json-report",
                f"--json-report-file={report_path}",
            ]
            if headed:
                cmd += ["--headed", "--slowmo=500"]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180 if headed else 120,
            )

            status, stderr = ScriptExecutorService._parse_report(report_path, result)

        return status, result.stdout, stderr

    @staticmethod
    def _parse_report(report_path: Path, result: subprocess.CompletedProcess) -> tuple[str, str | None]:
        if not report_path.exists():
            return ("error", result.stderr or "pytest did not produce a report")

        with open(report_path) as f:
            report = json.load(f)

        tests = report.get("tests", [])
        if not tests:
            return ("error", result.stderr or "no tests collected")

        outcome = tests[0]["outcome"]
        stderr = None
        if outcome != "passed":
            call = tests[0].get("call", {})
            longrepr = call.get("longrepr")
            stderr = longrepr if isinstance(longrepr, str) else result.stderr

        return (outcome, stderr)


# Shared singleton so /generate-tests and /execute-tests see the same registry.
executor_service = ScriptExecutorService()
