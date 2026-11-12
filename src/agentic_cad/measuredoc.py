"""Let the model write the measurement adapter, because the schema varies per case.

`facts.json` is not one schema. The top-level keys are stable across the practice
set, but the entries are not: `cylindrical_holes_and_bores` carries an extra
`more_not_listed` field on the cylinder head, `face_types` lists a different set of
surface species per part, and the radius and angle dictionaries are keyed
`{}` / `{15.25}` / `{1.0, 1.5, 2.0, ...}` depending on the part. A fixed measurer
written here silently drops whatever it did not anticipate -- which is the same
class of failure as hand-writing the comparison, one layer down.

So the agent writes it, per case, from the input's own structure:

  1. `scaffold()` hands the model the shape of facts.json with every number
     redacted. It can see the keys, the nesting and the list lengths, and it can
     see no measurement at all. That is the point: the numbers it emits cannot have
     been copied, because it never had them.
  2. The model writes `measure_result.py`, exposing `measure(shape) -> dict`.
  3. `run_measurer()` imports the produced STEP itself and calls that function. The
     module is never given a path to facts.json and is refused any import that could
     read one.
  4. `check_structure()` compares the produced document's shape with the input's, so
     a measurer that quietly omits a family is caught rather than believed.
  5. The values are then compared by `factscompare`, which walks the reference
     document and knows nothing about what the fields mean.

The model proposes; the harness disposes.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

# Anything that could reach facts.json, or the filesystem at all, is refused in the
# measurer. It has one job and it does not need I/O to do it.
FORBIDDEN_CALLS = {
    "open", "exec", "eval", "compile", "__import__", "input",
    "system", "popen", "run", "call", "check_output", "loads", "load",
}
FORBIDDEN_MODULES = {
    "os", "sys", "subprocess", "shutil", "pathlib", "io", "json",
    "urllib", "requests", "socket", "pickle", "importlib",
}
ALLOWED_IMPORT_ROOTS = {"build123d", "math", "itertools", "numpy", "typing", "OCP"}
REQUIRED_FUNCTION = "measure"


# --------------------------------------------------------------------------- #
# the redacted scaffold the model gets to see
# --------------------------------------------------------------------------- #


def scaffold(value: Any) -> Any:
    """The structure of a facts document with every number removed.

    Numbers become `null` so the shapes stay legible; strings survive only where
    they identify a family (an axis label, a surface type), and prose is dropped.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return None
    if isinstance(value, str):
        # Keep short identifiers such as "X", "concave", "convex round"; drop prose.
        return value if len(value) <= 24 else None
    if isinstance(value, dict):
        return {key: scaffold(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [scaffold(item) for item in value]
    return None


def _walk_numbers(value: Any) -> list[Any]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [value]
    if isinstance(value, dict):
        return [v for item in value.values() for v in _walk_numbers(item)]
    if isinstance(value, list):
        return [v for item in value for v in _walk_numbers(item)]
    return []


# --------------------------------------------------------------------------- #
# structural agreement
# --------------------------------------------------------------------------- #


def check_structure(reference: Any, produced: Any, path: str = "", depth: int = 0) -> list[str]:
    """Report where the produced document does not have the reference's *family* shape.

    Structure means: the document has the same top-level families, and each family is
    the same kind of container. It deliberately stops there.

    Everything below a family is a value, and values belong to `factscompare`. The
    first version recursed all the way down and reported
    `face_types.BSPLINE missing from the measured document` for a part whose
    `face_types` simply had no BSPLINE faces -- while the comparator was, correctly,
    reporting `face_types[BSPLINE] expected 222 actual 0` on the same run. One gap
    reported twice, in the wrong vocabulary, is noise that buries the real finding.

    What *is* structure, and is reported:

      * a top-level family that is absent
      * a family of the wrong container kind (a list where the facts have an object)
      * a feature family the measurer did not attempt at all, i.e. facts declare
        entries and the measured list is empty -- that is a gap in the adapter rather
        than a disagreement about geometry
    """
    problems: list[str] = []
    where = path or "<root>"

    if depth == 0:
        if not isinstance(reference, dict):
            return []
        if not isinstance(produced, dict):
            return [f"{where}: expected an object, got {type(produced).__name__}"]
        for key, value in reference.items():
            if key.startswith("_"):
                continue
            if key not in produced:
                problems.append(f"{key}: family missing from the measured document")
                continue
            problems.extend(check_structure(value, produced[key], key, depth + 1))
        for key in produced:
            if key not in reference:
                problems.append(f"{key}: family in the measured document that facts.json does not have")
        return problems

    kind_mismatch = (
        (isinstance(reference, dict) and not isinstance(produced, dict))
        or (isinstance(reference, list) and not isinstance(produced, list))
        or (isinstance(reference, (int, float)) and not isinstance(reference, bool)
            and (not isinstance(produced, (int, float)) or isinstance(produced, bool)))
    )
    if kind_mismatch:
        return [f"{where}: expected {type(reference).__name__}, got {type(produced).__name__}"]

    if isinstance(reference, list) and reference and not produced:
        problems.append(
            f"{where}: facts declare {len(reference)} entr"
            f"{'y' if len(reference) == 1 else 'ies'} and the measured document has none "
            f"-- the measurer did not attempt this family"
        )
    return problems


# --------------------------------------------------------------------------- #
# refusing a measurer that could cheat
# --------------------------------------------------------------------------- #


def audit_measurer(source: str) -> list[str]:
    """Reject a measurer that could read facts.json or otherwise lie.

    The module is handed a live shape and nothing else. If it opens the case
    directory it could copy the expected numbers instead of measuring, so the whole
    filesystem and any dynamic evaluation is refused outright.
    """
    violations: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [f"the measurer does not parse: {error}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    violations.append(f"import {alias.name} is not allowed in a measurer")
                elif root not in ALLOWED_IMPORT_ROOTS:
                    violations.append(
                        f"import {alias.name} is not allowed; permitted roots are "
                        f"{sorted(ALLOWED_IMPORT_ROOTS)}"
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_MODULES:
                violations.append(f"from {node.module} import ... is not allowed in a measurer")
            elif root and root not in ALLOWED_IMPORT_ROOTS:
                violations.append(
                    f"from {node.module} import ... is not allowed; permitted roots are "
                    f"{sorted(ALLOWED_IMPORT_ROOTS)}"
                )
        elif isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in FORBIDDEN_CALLS:
                violations.append(f"calling {name}() is not allowed in a measurer")

    has_measure = any(
        isinstance(node, ast.FunctionDef) and node.name == REQUIRED_FUNCTION for node in tree.body
    )
    if not has_measure:
        violations.append(f"the measurer must define `def {REQUIRED_FUNCTION}(shape):`")
    return violations


# --------------------------------------------------------------------------- #
# running it
# --------------------------------------------------------------------------- #


def run_measurer(source: str, shape: Any, work_dir: Path) -> tuple[dict[str, Any] | None, str]:
    """Execute the model's measurer against a shape and return its document."""
    violations = audit_measurer(source)
    if violations:
        return None, "the measurer was refused before it ran:\n" + "\n".join(f"- {v}" for v in violations)

    work_dir.mkdir(parents=True, exist_ok=True)
    module_path = work_dir / "measure_result.py"
    module_path.write_text(source, encoding="utf-8")

    namespace: dict[str, Any] = {"__name__": "measure_result", "__file__": str(module_path)}
    try:
        exec(compile(source, str(module_path), "exec"), namespace)  # noqa: S102 - audited above
        function = namespace.get(REQUIRED_FUNCTION)
        document = function(shape)
    except Exception as error:  # noqa: BLE001 - a bad measurer must not abort the case
        import traceback

        return None, f"the measurer raised {type(error).__name__}: {error}\n{traceback.format_exc()[-1200:]}"

    if not isinstance(document, dict):
        return None, f"the measurer returned {type(document).__name__}, expected a dict"
    try:
        json.dumps(document)
    except TypeError as error:
        return None, f"the measurer's document is not JSON serialisable: {error}"
    return document, ""


def write_document(document: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=1, ensure_ascii=False), encoding="utf-8")
