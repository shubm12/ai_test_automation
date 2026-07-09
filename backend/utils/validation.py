"""Anti-truncation / anti-hallucination safety net for generated code.

Every generated script must parse as valid Python AND contain at least one
real pytest test function before it's trusted. ast.parse() alone is not
enough: an empty string (a failure mode of reasoning models that exhaust
their completion budget) or a file of nothing but comments parses cleanly.
A failure here is almost always a truncated/degenerate LLM response, so we
retry generation itself (not re-parse the same broken output).
"""
import ast
from typing import Callable


def validate_test_code(code: str) -> tuple[bool, str | None]:
    """Valid = parses as Python AND defines at least one `def test_*(...)`
    containing at least one real statement besides docstrings/pass."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"not valid Python: {e}"

    test_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    if not test_functions:
        return False, "no `def test_*` function found (empty or degenerate generation)"

    for fn in test_functions:
        real_statements = [
            stmt
            for stmt in fn.body
            if not isinstance(stmt, ast.Pass)
            and not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        ]
        if real_statements:
            return True, None

    return False, "test function body contains no executable statements"


def validate_and_retry(generate_fn: Callable[[], str], *, max_retries: int = 2) -> str:
    """Call generate_fn() until it returns a valid test script or retries are exhausted."""
    last_error = None
    last_code = ""
    for attempt in range(max_retries + 1):
        code = generate_fn()
        ok, error = validate_test_code(code)
        if ok:
            return code
        last_error = error
        last_code = code

    raise ValueError(
        f"Generated code failed validation after {max_retries + 1} attempts: {last_error}\n---\n{last_code}"
    )
