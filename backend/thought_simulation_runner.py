import ast
import contextlib
import io
import json
import os
import sys
import traceback
import uuid
from typing import Any


DEFAULT_OUTPUT_MAX_CHARS = 12000
MAX_CODE_CHARS = 12000
FORBIDDEN_NAMES = {
    "__import__",
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "help",
    "breakpoint",
    "memoryview",
}
FORBIDDEN_ATTRS = {
    "system",
    "popen",
    "run",
    "Popen",
    "fork",
    "spawn",
    "remove",
    "unlink",
    "rmdir",
    "mkdir",
    "makedirs",
    "rename",
    "replace",
    "open",
    "read",
    "read_text",
    "read_bytes",
    "write",
    "write_text",
    "write_bytes",
    "load",
    "loads",
    "loadtxt",
    "genfromtxt",
    "fromfile",
    "tofile",
    "save",
    "savez",
    "savez_compressed",
    "dump",
    "dumps",
    "connect",
    "socket",
    "request",
    "urlopen",
    "post",
    "get",
    "put",
    "delete",
    "patch",
}
SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "complex": complex,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "print": print,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}

# Human-readable fix hints for each validation error code
_VALIDATION_HINTS = {
    "import_statements_are_disabled": (
        "Remove all import statements. "
        "The following aliases are pre-loaded: np (NumPy), sp (SymPy), "
        "sc (SciPy), torch (PyTorch), qt (QuTiP), ep (EinsteinPy), "
        "plt (matplotlib.pyplot), display_plot. Use them directly."
    ),
    "while_loops_are_disabled": (
        "Replace the while loop with a for loop over a range or iterable."
    ),
    "with_statements_are_disabled": (
        "Remove the 'with' statement. Use direct function calls instead."
    ),
    "async_with_is_disabled": "Remove async with statements.",
    "class_definitions_are_disabled": (
        "Remove class definitions. Use plain functions and data structures instead."
    ),
    "lambda_is_disabled": (
        "Replace the lambda with a named def function."
    ),
    "await_is_disabled": "Remove await expressions; the sandbox is synchronous.",
    "yield_is_disabled": (
        "Remove yield statements. Collect results into a list instead."
    ),
    "global_statements_are_disabled": "Remove global statements.",
    "nonlocal_statements_are_disabled": "Remove nonlocal statements.",
}


class ThoughtSimulationValidationError(Exception):
    def __init__(self, code: str, lineno: int | None = None, line_text: str | None = None):
        super().__init__(code)
        self.code = code
        self.lineno = lineno
        self.line_text = line_text

    def to_reason(self) -> str:
        parts = [self.code]
        if self.lineno is not None:
            parts.append(f"line {self.lineno}")
        if self.line_text:
            parts.append(f"offending_code: {self.line_text.strip()!r}")
        hint_key = self.code.split(":")[0]
        hint = _VALIDATION_HINTS.get(hint_key)
        if hint:
            parts.append(f"fix: {hint}")
        return " | ".join(parts)


def _source_line(source_lines: list[str], lineno: int | None) -> str | None:
    if lineno is None or not source_lines:
        return None
    idx = lineno - 1
    if 0 <= idx < len(source_lines):
        return source_lines[idx]
    return None


class ThoughtSimulationValidator(ast.NodeVisitor):
    def __init__(self, source_lines: list[str]):
        self._lines = source_lines

    def _raise(self, code: str, node: ast.AST) -> None:
        lineno: int | None = getattr(node, "lineno", None)
        line_text = _source_line(self._lines, lineno)
        raise ThoughtSimulationValidationError(code, lineno=lineno, line_text=line_text)

    def visit_Import(self, node: ast.Import) -> Any:
        self._raise("import_statements_are_disabled", node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        self._raise("import_statements_are_disabled", node)

    def visit_Global(self, node: ast.Global) -> Any:
        self._raise("global_statements_are_disabled", node)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> Any:
        self._raise("nonlocal_statements_are_disabled", node)

    def visit_While(self, node: ast.While) -> Any:
        self._raise("while_loops_are_disabled", node)

    def visit_With(self, node: ast.With) -> Any:
        self._raise("with_statements_are_disabled", node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> Any:
        self._raise("async_with_is_disabled", node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self._raise("class_definitions_are_disabled", node)

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        self._raise("lambda_is_disabled", node)

    def visit_Await(self, node: ast.Await) -> Any:
        self._raise("await_is_disabled", node)

    def visit_Yield(self, node: ast.Yield) -> Any:
        self._raise("yield_is_disabled", node)

    def visit_YieldFrom(self, node: ast.YieldFrom) -> Any:
        self._raise("yield_is_disabled", node)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id.startswith("_") or node.id in FORBIDDEN_NAMES:
            self._raise(f"name_not_allowed:{node.id}", node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        if node.attr.startswith("_") or node.attr in FORBIDDEN_ATTRS:
            self._raise(f"attribute_not_allowed:{node.attr}", node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        func = node.func
        if isinstance(func, ast.Name) and func.id in FORBIDDEN_NAMES:
            self._raise(f"call_not_allowed:{func.id}", node)
        if isinstance(func, ast.Attribute) and (
            func.attr.startswith("_") or func.attr in FORBIDDEN_ATTRS
        ):
            self._raise(f"call_not_allowed:{func.attr}", node)
        self.generic_visit(node)


def _truncate_output(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    suffix = "\n...[truncated]"
    keep = max(0, max_chars - len(suffix))
    return text[:keep].rstrip() + suffix, True


def _load_request() -> dict[str, Any]:
    if len(sys.argv) < 2:
        return {}
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_display_plot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def display_plot(plt_obj, caption: str = "Figure") -> None:
        filename = f"sim_{uuid.uuid4().hex[:8]}.png"
        assets_dir = os.path.join(os.path.dirname(__file__), "data", "dream_assets")
        os.makedirs(assets_dir, exist_ok=True)
        filepath = os.path.join(assets_dir, filename)
        plt_obj.savefig(filepath, bbox_inches="tight")
        print(f"\n![{caption}](/dream_assets/{filename})\n")
        plt_obj.clf()
        plt_obj.close("all")

    return plt, display_plot


def _format_runtime_error(exc: Exception, code: str) -> str:
    """Return a compact error string with line number and offending line when available."""
    tb = traceback.extract_tb(exc.__traceback__)
    # Find the frame that refers to the sandboxed code
    sim_frame = next(
        (f for f in reversed(tb) if f.filename == "<thought_simulation>"),
        None,
    )
    parts = [type(exc).__name__ + ": " + str(exc)]
    if sim_frame is not None:
        parts.append(f"line {sim_frame.lineno}")
        source_lines = code.splitlines()
        line_text = _source_line(source_lines, sim_frame.lineno)
        if line_text:
            parts.append(f"offending_code: {line_text.strip()!r}")
    return " | ".join(parts)


def _execute(code: str, output_max_chars: int) -> dict[str, Any]:
    if not code.strip():
        return {"status": "failed", "reason": "missing_code"}
    if len(code) > MAX_CODE_CHARS:
        return {"status": "failed", "reason": "code_too_large"}

    source_lines = code.splitlines()

    try:
        tree = ast.parse(code, mode="exec")
        ThoughtSimulationValidator(source_lines).visit(tree)
        compiled = compile(tree, "<thought_simulation>", "exec")
    except ThoughtSimulationValidationError as exc:
        return {"status": "failed", "reason": exc.to_reason()}
    except SyntaxError as exc:
        line_text = _source_line(source_lines, exc.lineno)
        parts = [f"syntax_error:{exc.msg}"]
        if exc.lineno is not None:
            parts.append(f"line {exc.lineno}")
        if line_text:
            parts.append(f"offending_code: {line_text.strip()!r}")
        return {"status": "failed", "reason": " | ".join(parts)}

    try:
        import numpy as np
        import sympy as sp
        import scipy as sc
        import torch
        import qutip as qt
        import einsteinpy as ep
        plt, display_plot = _build_display_plot()
    except Exception as exc:
        return {"status": "failed", "reason": f"dependency_error:{exc}"}

    namespace = {
        "np": np,
        "sp": sp,
        "sc": sc,
        "torch": torch,
        "qt": qt,
        "ep": ep,
        "plt": plt,
        "display_plot": display_plot,
    }
    globals_dict = {
        "__builtins__": SAFE_BUILTINS,
        "__name__": "__thought_simulation__",
    }

    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            exec(compiled, globals_dict, namespace)
    except Exception as exc:
        return {"status": "failed", "reason": _format_runtime_error(exc, code)}

    output = stdout.getvalue() or "Simulation completed successfully with no standard output."
    output, truncated = _truncate_output(output, max(256, int(output_max_chars or DEFAULT_OUTPUT_MAX_CHARS)))
    return {
        "status": "success",
        "reason": "ok",
        "output": output,
        "truncated": truncated,
    }


def main() -> int:
    request = _load_request()
    objective = str(request.get("objective") or "").strip()
    code = str(request.get("code") or "")
    output_max_chars = int(request.get("output_max_chars") or DEFAULT_OUTPUT_MAX_CHARS)
    payload = _execute(code, output_max_chars)
    payload["objective"] = objective
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
