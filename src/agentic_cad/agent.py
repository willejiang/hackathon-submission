"""The reconstruction loop for one test case.

Per case:

  1. ask for a module (or load one, when AGENTIC_CAD_SPEC_DIR is set)
  2. provenance check            -> rejects unexplained numbers before building
  3. build                       -> exactly one connected solid
  4. measure independently       -> compare with facts.json
  5. render eight silhouettes    -> compare with the reference views
  6. on disagreement, classify the failure and try again, bounded
  7. export the best candidate seen, always

Step 7 is not optional. A missing file scores zero for that case, so a bad
candidate always beats no candidate; the loop keeps the best one it managed.

Acceptance gates, in the language of the brief:

  submission gate   exactly one STEP file per case, one solid
  geometry gate     valid B-rep, one connected solid
  facts gate        every gating fact from facts.json matches
  projection gate   mean orthographic silhouette IoU above a threshold
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import cad, diagnose, factsgen, imagecmp, provenance, raster
from .gt import GroundTruth
from .llm import LlmClient, LlmConfig, extract_code, extract_prose
from .prompts import (
    DIAGNOSIS_SYSTEM,
    SYSTEM_PROMPT,
    build_diagnosis_prompt,
    build_user_prompt,
)

DEFAULT_ATTEMPTS = 3
DEFAULT_IOU_THRESHOLD = 0.93


@dataclass
class Attempt:
    index: int
    source: str
    accepted: bool = False
    build_ok: bool = False
    build_error: str = ""
    measured: dict | None = None
    facts: factsgen.Comparison | None = None
    images: imagecmp.Comparison | None = None
    provenance_ok: bool = False
    provenance_text: str = ""
    score: tuple = (999, 0.0, 999.0)

    @property
    def gating_failures(self) -> int:
        return len(self.facts.gating_failures) if self.facts else 999


@dataclass
class CaseResult:
    name: str
    output_path: Path
    attempts: list[Attempt] = field(default_factory=list)
    elapsed_s: float = 0.0
    accepted: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def best(self) -> Attempt | None:
        return self.attempts[-1] if self.attempts else None

    def summary(self) -> str:
        if not self.attempts:
            return f"{self.name}: no candidate produced"
        best = self.best
        assert best is not None
        facts_line = "facts n/a" if best.facts is None else (
            "facts PASS" if best.facts.ok else f"facts FAIL ({best.gating_failures} gating)"
        )
        image_line = "images n/a" if best.images is None else f"IoU {best.images.mean_iou_ortho:.3f}"
        return (
            f"{self.name}: {'ACCEPTED' if self.accepted else 'best-effort'} after "
            f"{len(self.attempts)} attempt(s), {facts_line}, {image_line}, {self.elapsed_s:.1f}s"
        )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _load_spec_from_dir(directory: Path, case_name: str) -> str | None:
    for candidate in (directory / f"{case_name}.py", directory / f"{case_name.removeprefix('test_case_')}.py"):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return None


def reconstruct(
    gt: GroundTruth,
    *,
    images_dir: Path,
    output_path: Path,
    work_dir: Path,
    deadline: float,
    client: LlmClient | None = None,
) -> CaseResult:
    """Reconstruct one part and write its STEP file."""
    started = time.time()
    result = CaseResult(name=gt.name, output_path=output_path)
    work_dir.mkdir(parents=True, exist_ok=True)

    attempts_allowed = _env_int("AGENTIC_CAD_ATTEMPTS", DEFAULT_ATTEMPTS)
    iou_threshold = _env_float("AGENTIC_CAD_IOU", DEFAULT_IOU_THRESHOLD)
    spec_dir = os.environ.get("AGENTIC_CAD_SPEC_DIR", "").strip()
    spec_dir_path = Path(spec_dir) if spec_dir else None

    diagnostics = ""
    best_shape = None
    best_attempt: Attempt | None = None

    for index in range(1, attempts_allowed + 1):
        if time.time() >= deadline:
            result.notes.append(f"deadline reached before attempt {index}")
            break

        # ---- obtain a candidate module -------------------------------------
        if spec_dir_path is not None:
            source = _load_spec_from_dir(spec_dir_path, gt.name)
            if source is None:
                result.notes.append(f"no spec file for {gt.name} in {spec_dir_path}")
                break
        elif client is None:
            result.notes.append("no LLM configured (OPENAI_BASE_URL/OPENAI_MODEL unset) and no spec dir")
            break
        else:
            try:
                reply = client.chat(
                    system=SYSTEM_PROMPT,
                    user=build_user_prompt(gt, attempt=index, diagnostics=diagnostics),
                    images=list(gt.views) + ([gt.context] if gt.context else []),
                )
            except Exception as error:  # noqa: BLE001 - a provider outage must not abort the case
                result.notes.append(f"attempt {index}: LLM error: {error}")
                break
            source = extract_code(reply)
            notes = extract_prose(reply)
            if notes:
                result.notes.append(f"attempt {index} notes: {notes[:400]}")
            if not source:
                diagnostics = "Your reply contained no Python module. Return exactly one ```python block."
                continue

        attempt = Attempt(index=index, source=source)
        result.attempts.append(attempt)

        # ---- 2. provenance --------------------------------------------------
        prov = provenance.check(gt, source)
        attempt.provenance_ok = prov.ok
        attempt.provenance_text = prov.render()
        if not prov.ok:
            (work_dir / f"attempt_{index}_provenance.txt").write_text(prov.render(), encoding="utf-8")
            diagnostics = (
                "The previous attempt was rejected before it was built, because it broke the "
                "parameter-provenance rule. Fix exactly these and return the whole module again:\n"
                + prov.render()
            )
            continue

        # ---- 3. build -------------------------------------------------------
        build = cad.run_module(gt, source)
        attempt.build_ok = build.ok
        if not build.ok:
            attempt.build_error = build.failure_text()
            diagnostics = (
                "The previous attempt failed to build. Fix this error and return the whole module:\n"
                + attempt.build_error
            )
            continue

        shape = build.shape
        (work_dir / f"attempt_{index}.py").write_text(source, encoding="utf-8")

        # ---- 4. measure -----------------------------------------------------
        measured = factsgen.measure(shape)
        attempt.measured = measured
        attempt.facts = factsgen.compare(gt, measured)

        # ---- 5. render and compare -----------------------------------------
        t0 = time.time()
        rendered = raster.render_all(shape)
        attempt.images = imagecmp.compare_all(images_dir, rendered)
        render_s = time.time() - t0
        if render_s > 20:
            result.notes.append(f"attempt {index}: rendering took {render_s:.1f}s")

        volume_error = 0.0
        if gt.volume:
            volume_error = abs(measured["volume_mm3"] - gt.volume) / gt.volume
        attempt.score = (
            attempt.gating_failures,
            -attempt.images.mean_iou_ortho,
            volume_error,
        )

        (work_dir / f"attempt_{index}_report.json").write_text(
            json.dumps(
                {
                    "attempt": index,
                    "accepted": False,
                    "provenance": attempt.provenance_text,
                    "measured": measured,
                    "facts": [
                        {
                            "name": c.name,
                            "expected": c.expected,
                            "actual": c.actual,
                            "verdict": c.verdict,
                            "gating": c.gating,
                        }
                        for c in attempt.facts.checks
                    ],
                    "images": [
                        {"stem": v.stem, "iou": round(v.iou, 4), "over": round(v.overfill, 4),
                         "under": round(v.underfill, 4)}
                        for v in attempt.images.views
                    ],
                },
                indent=1,
            ),
            encoding="utf-8",
        )

        # ---- 7. track the best ---------------------------------------------
        if best_attempt is None or attempt.score < best_attempt.score:
            best_attempt = attempt
            best_shape = shape

        # ---- acceptance -----------------------------------------------------
        if attempt.facts.ok and attempt.images.mean_iou_ortho >= iou_threshold:
            attempt.accepted = True
            result.accepted = True
            break

        # ---- 6. classify and prepare the retry ------------------------------
        diag = diagnose.classify(gt, attempt.facts, attempt.images)
        deterministic = diag.render()
        if client is not None:
            try:
                model_view = client.chat(
                    system=DIAGNOSIS_SYSTEM,
                    user=build_diagnosis_prompt(
                        gt,
                        module_source=source,
                        measured=json.dumps(measured, indent=1),
                        comparison=attempt.images.render(),
                    ),
                )
                diagnostics = (
                    f"{model_view}\n\nDeterministic check of the same candidate:\n{deterministic}"
                )
            except Exception:  # noqa: BLE001 - fall back to the deterministic diagnosis
                diagnostics = deterministic
        else:
            diagnostics = deterministic

    # ---- export the best candidate, even when nothing was accepted ---------
    if best_attempt is not None and best_shape is not None:
        try:
            cad.export_step(best_shape, output_path)
        except Exception as error:  # noqa: BLE001
            result.notes.append(f"STEP export failed: {error}")
    elif spec_dir_path is None and client is None:
        result.notes.append("nothing exported: no candidate was produced")

    result.elapsed_s = time.time() - started
    if best_attempt is not None:
        summary = {
            "case": gt.name,
            "accepted": result.accepted,
            "attempts": len(result.attempts),
            "best_attempt": best_attempt.index,
            "gating_failures": best_attempt.gating_failures,
            "mean_iou_ortho": round(best_attempt.images.mean_iou_ortho, 4) if best_attempt.images else None,
            "elapsed_s": round(result.elapsed_s, 1),
            "notes": result.notes,
        }
        (work_dir / "case_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    return result


def make_client() -> LlmClient | None:
    """Build the client from the environment, or None when unconfigured."""
    config = LlmConfig.from_env()
    return LlmClient(config) if config is not None else None
