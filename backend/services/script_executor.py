"""Stage 3 — execute a generated script and report a per-test-case result.

Uses pytest-json-report instead of scraping stdout, so status parsing is
structural rather than regex-based.
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

        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "report.json"
            result = subprocess.run(
                [
                    "pytest",
                    str(file_path),
                    "-v",
                    "--tb=short",
                    "--headed",
                    "--slowmo=500",
                    "--json-report",
                    f"--json-report-file={report_path}",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            status, stderr = self._parse_report(report_path, result)

        return ExecuteResult(
            title=title,
            file=file_path.name,
            status=status,
            stdout=result.stdout,
            stderr=stderr,
        )

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
            stderr = call.get("longrepr") or result.stderr

        return (outcome, stderr)


# Shared singleton so /generate-tests and /execute-tests see the same registry.
executor_service = ScriptExecutorService()
