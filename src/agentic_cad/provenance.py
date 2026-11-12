"""Static enforcement of the parameter-provenance rules.

The prompt asks the model to express every dimension as a grounded value or a
named formula. That is worthless if nothing checks it, so this module does: it
parses the generated module and rejects numeric literals that cannot be traced to
the authoritative inputs.

The two rules, restated:

  derive()  a numeric literal is allowed when it appears in facts.json /
            description.md, or is structural (0, 1, 2, 3, -1, 90, 180, 270)
  build()   only structural literals; every dimension must come from the
            parameter dict

Everything else is reported with its line number so the retry prompt can name the
offending code instead of restating the whole rule.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .gt import GroundTruth

# Indices, halves, and right-angle rotations. Not dimensions.
STRUCTURAL_LITERALS: frozenset[float] = frozenset({0.0, 1.0, 2.0, 3.0, -1.0, 90.0, 180.0, 270.0, -90.0, -180.0, -270.0})

# Tolerance when matching a derived literal against a value in the fact sheet.
_LITERAL_TOLERANCE = 1e-6

FORBIDDEN_CALLS = {
    "open",            # the runner owns all I/O
    "exec",
    "eval",
    "compile",
    "__import__",
    "export_step",     # the runner exports
    "write",
    "write_text",
    "write_bytes",
    "unlink",
    "remove",
    "rmtree",
    "system",
    "popen",
    "run",
    "call",
    "check_output",
}

ALLOWED_IMPORT_ROOTS = {"build123d", "math", "itertools", "numpy", "typing"}


@dataclass
class Violation:
    rule: str
    message: str
    line: int

    def render(self, source_lines: list[str]) -> str:
        snippet = ""
        if 0 < self.line <= len(source_lines):
            snippet = source_lines[self.line - 1].strip()
        return f"  line {self.line}: {self.message}\n      {snippet}" if snippet else f"  line {self.line}: {self.message}"


@dataclass
class ProvenanceReport:
    ok: bool
    violations: list[Violation] = field(default_factory=list)
    estimated: list[tuple[int, str]] = field(default_factory=list)
    assumed: list[tuple[int, str]] = field(default_factory=list)
    has_derive: bool = False
    has_build: bool = False
    has_notes: bool = False

    source: str = ""

    def render(self) -> str:
        if self.ok:
            extra = ""
            if self.estimated or self.assumed:
                extra = f" ({len(self.estimated)} estimated, {len(self.assumed)} assumed)"
            return f"provenance: ok{extra}"
        # `violations` holds Violation objects, not strings. Joining them directly
        # raised TypeError, so every rejected module came back to the model as a
        # Python traceback instead of a usable message -- which is why a run against
        # the bracket spent its budget writing probe scripts to discover the rule by
        # experiment.
        lines = [self.render_violation(v) for v in self.violations]
        header = f"provenance: FAILED ({len(lines)} violation{'s' if len(lines) != 1 else ''})"
        rewrite = (
            "\nA literal in build() has to reach the shape through the parameter dict: "
            "write Box(p['x'], p['y'], p['z']), not Box(11, 20, 30). A literal in "
            "derive() is legal when the value is in facts.json or the brief."
            if any(v.rule == "provenance" and "build()" in v.message for v in self.violations)
            else ""
        )
        return header + "\n" + "\n".join(lines) + rewrite

    def render_violation(self, violation: Violation) -> str:
        source_lines = self.source.splitlines()
        return violation.render(source_lines)


def _literal_value(node: ast.AST) -> float | None:
    """Numeric value of a constant, folding a unary +/- in front of it."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _literal_value(node.operand)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    return None


def _is_structural(value: float) -> bool:
    return any(abs(value - allowed) < _LITERAL_TOLERANCE for allowed in STRUCTURAL_LITERALS)


def _matches_ground_truth(value: float, known: set[float]) -> bool:
    """A literal in `derive()` is legal only when it IS a value in the inputs.

    Deliberately exact: writing `12.7` when the brief says the diameter is 25.4
    is the folded form of `25.4 / 2`, and the whole point of the discipline is
    that folded constants are how a derivation quietly stops being a derivation.
    The fix is to write the division, not to widen the check.
    """
    if _is_structural(value):
        return True
    return any(abs(value - candidate) <= _LITERAL_TOLERANCE for candidate in known)


def check(gt: GroundTruth, source: str) -> ProvenanceReport:
    """Validate one generated module against the provenance rules."""
    report = ProvenanceReport(ok=True, source=source)
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        report.ok = False
        report.violations.append(Violation("syntax", f"module does not parse: {error.msg}", error.lineno or 1))
        return report

    source_lines = source.splitlines()
    known = gt.known_numbers()

    # Statement-level scans ---------------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORT_ROOTS:
                    report.violations.append(
                        Violation("import", f"import of '{alias.name}' is not allowed; only {sorted(ALLOWED_IMPORT_ROOTS)}", node.lineno)
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in ALLOWED_IMPORT_ROOTS:
                report.violations.append(
                    Violation("import", f"from '{node.module}' is not allowed; only {sorted(ALLOWED_IMPORT_ROOTS)}", node.lineno)
                )
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
            if name in FORBIDDEN_CALLS:
                report.violations.append(
                    Violation("io", f"'{name}()' is not allowed; the runner owns all I/O", node.lineno)
                )

    # Module contract --------------------------------------------------------
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    report.has_derive = "derive" in functions
    report.has_build = "build" in functions
    report.has_notes = any(
        isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NOTES" for t in node.targets)
        for node in tree.body
    )
    if not report.has_derive:
        report.violations.append(Violation("contract", "module must define `def derive(facts)`", 1))
    if not report.has_build:
        report.violations.append(Violation("contract", "module must define `def build(p)`", 1))

    # Per-function literal rules --------------------------------------------
    def scan(func: ast.FunctionDef, *, allow_grounded: bool) -> None:
        for node in ast.walk(func):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                continue
            value = _literal_value(node)
            if value is None:
                continue
            if _is_structural(value):
                continue
            if allow_grounded and _matches_ground_truth(value, known):
                continue
            where = "derive()" if allow_grounded else "build()"
            if allow_grounded:
                message = (
                    f"{value:g} in {where} is not in facts.json or the brief; take it from "
                    f"`facts`, or write it as a formula over values that are"
                )
            else:
                message = (
                    f"{value:g} in {where} is not structural; build() may only use "
                    f"0/1/2/3/-1/90/180/270, so pass this through `derive()` instead"
                )
            report.violations.append(Violation("provenance", message, node.lineno))

    if report.has_derive:
        scan(functions["derive"], allow_grounded=True)
    if report.has_build:
        scan(functions["build"], allow_grounded=False)

    # Declared estimates and assumptions ------------------------------------
    for index, line in enumerate(source_lines, start=1):
        lowered = line.lower()
        if "# estimated" in lowered or "#estimated" in lowered:
            report.estimated.append((index, line.strip()))
        if "# assumed" in lowered or "#assumed" in lowered:
            report.assumed.append((index, line.strip()))

    report.ok = not report.violations
    return report


def check_file(gt: GroundTruth, path: Path) -> ProvenanceReport:
    return check(gt, path.read_text(encoding="utf-8"))
