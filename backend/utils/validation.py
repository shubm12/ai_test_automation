"""Anti-truncation / anti-hallucination safety net for generated code.

Every generated script must parse as valid Python before it's trusted. A
SyntaxError here is almost always a truncated LLM response, not a one-off
fluke, so we retry generation itself (not re-parse the same broken output).
"""
import ast
from typing import Callable


def validate_python(code: str) -> tuple[bool, str | None]:
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, str(e)


def validate_and_retry(generate_fn: Callable[[], str], *, max_retries: int = 2) -> str:
    """Call generate_fn() until it returns syntactically valid Python or retries are exhausted."""
    last_error = None
    last_code = ""
    for attempt in range(max_retries + 1):
        code = generate_fn()
        ok, error = validate_python(code)
        if ok:
            return code
        last_error = error
        last_code = code

    raise ValueError(
        f"Generated code failed ast.parse() after {max_retries + 1} attempts: {last_error}\n---\n{last_code}"
    )
