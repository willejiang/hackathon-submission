// Deterministic CAD tools + discipline skill for the reconstruction agent.
//
// Division of labour, which is the whole point of this plugin:
//
//   the model   decides what geometry to attempt, looks at the rendered views with
//               its own `read_image`, and interprets the numbers it gets back
//   the tools   build, measure, render and compare, exactly, in one call
//
// Nothing here asks the model to compute a volume or eyeball a silhouette overlap;
// those are Python. Nothing here decides what to try next; that is the model.
//
// Each tool shells out to `python -m agentic_cad.cli <tool> <json>` and returns a
// compact human-readable rendering of the JSON, because a model reads a table
// better than it reads serialised state.
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const pluginRoot = resolve(here, "..");
const repoRoot = resolve(pluginRoot, "..");

export const name = "agentic-cad-tools";
export const inject = ["tools", "skills"];

const PLUGIN_ID = "@agentic-cad/dsh-tools";

/** Run one CLI subcommand and parse its JSON. */
function runCli(config, tool, args) {
  return new Promise((resolvePromise) => {
    const python = config.python || process.env.AGENTIC_CAD_PYTHON || "python";
    const sourceDir = config.source_dir || process.env.AGENTIC_CAD_SRC || join(repoRoot, "src");
    const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };
    // Prefer the checkout over an installed copy, so tool code and repo code can
    // never disagree about which version is running.
    env.PYTHONPATH = env.PYTHONPATH ? `${sourceDir}${process.platform === "win32" ? ";" : ":"}${env.PYTHONPATH}` : sourceDir;

    const child = spawn(python, ["-m", "agentic_cad.cli", tool, JSON.stringify(args ?? {})], {
      cwd: process.cwd(), // the session workspace, where the agent writes solution.py
      env,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString("utf8"); });
    child.on("error", (error) => resolvePromise({ ok: false, error: `could not run ${python}: ${error.message}` }));
    child.on("close", (code) => {
      if (code !== 0 && !stdout.trim()) {
        resolvePromise({ ok: false, error: `cli exited ${code}`, stderr_tail: stderr.slice(-1500) });
        return;
      }
      try {
        resolvePromise(JSON.parse(stdout));
      } catch {
        resolvePromise({ ok: false, error: "cli returned non-JSON", stdout_tail: stdout.slice(-800), stderr_tail: stderr.slice(-800) });
      }
    });
  });
}

const text = (value) => [{ type: "text", text: value }];

/** Compact rendering of `cad_verify`. */
function renderVerify(value) {
  if (!value?.ok && value?.stage) return `FAILED in ${value.stage}: ${value.error ?? value.report}`;
  const lines = [value.table];
  if (value.gating_failures?.length) {
    lines.push("", `GATING FAILURES: ${value.gating_failures.join(", ")}`);
  } else {
    lines.push("", "All gating facts pass.");
  }
  if (value.advise) lines.push("", value.advise);
  return lines.join("\n");
}

/** Compact rendering of `cad_build`. */
function renderBuild(value) {
  if (!value?.ok) return `BUILD FAILED in ${value?.stage ?? "?"}: ${value?.error ?? value?.report ?? "unknown"}`;
  return [
    `built: ${value.solids} solid(s), volume ${value.volume_mm3} mm^3`,
    `bbox ${value.bounding_box_mm.x} x ${value.bounding_box_mm.y} x ${value.bounding_box_mm.z} mm`,
    `faces ${value.faces}, edges ${value.edges}, genus ${value.through_holes_genus}`,
    `face types ${JSON.stringify(value.face_types)}`,
    `cylinders ${JSON.stringify(value.cylinders)}`,
    value.provenance,
  ].join("\n");
}

/** Compact rendering of `cad_render`. */
function renderRender(value) {
  if (!value?.ok) return `RENDER FAILED in ${value?.stage ?? "?"}: ${value?.error ?? "unknown"}`;
  return [
    `mean IoU: orthographic ${value.mean_iou_ortho}, isometric ${value.mean_iou_iso}`,
    value.table,
    "",
    value.advise,
    "",
    "overfill = material you added that the reference does not have; underfill = material you are missing.",
  ].join("\n");
}

function toolDefinitions(config) {
  const build = (tool, args) => runCli(config, tool, args);

  return [
    {
      name: "cad_case_info",
      description:
        "Ground truth for this test case: the complete facts.json, the design brief, the eight view " +
        "image paths with their camera conventions, and the units. Call this first. " +
        "facts.json and the brief are authoritative and must not be changed.",
      parameters: {},
      output: { schema: { type: "object", additionalProperties: true }, render: (_a, v) => text(JSON.stringify(v, null, 1)) },
      execute: async () => build("case", {}),
    },
    {
      name: "cad_build",
      description:
        "Run your module (a file with derive(facts) and build(p)) through the provenance check and the " +
        "CAD kernel. Returns the produced solid's own numbers: volume, bounding box, solids, faces, " +
        "edges, genus -- or the exact provenance violation or build error. Use this to find out what " +
        "your geometry actually is before you compare it to anything.",
      parameters: {
        path: { type: "string", required: true, description: "File holding the module, e.g. solution.py (relative to the workspace)" },
      },
      output: { schema: { type: "object", additionalProperties: true }, render: (_a, v) => text(renderBuild(v)) },
      execute: async (args) => build("build", args),
    },
    {
      name: "cad_verify",
      description:
        "Compare the solid your module builds against every fact in facts.json: bounding box, volume, " +
        "surface area, solid count, genus, face and edge counts, face-type histogram and the bore " +
        "inventory. Rows marked * are gating and decide acceptance; the rest are advisory evidence. " +
        "This measures the produced geometry, not your parameters.",
      parameters: {
        path: { type: "string", required: true, description: "File holding the module, e.g. solution.py" },
      },
      output: { schema: { type: "object", additionalProperties: true }, render: (_a, v) => text(renderVerify(v)) },
      execute: async (args) => build("verify", args),
    },
    {
      name: "cad_render",
      description:
        "Rasterise your solid from the same eight camera directions as the reference renders and report " +
        "silhouette overlap per view (IoU, overfill, underfill, aspect). Use it to test whether your " +
        "shape matches the pictures, after the numbers already agree.",
      parameters: {
        path: { type: "string", required: true, description: "File holding the module, e.g. solution.py" },
      },
      output: { schema: { type: "object", additionalProperties: true }, render: (_a, v) => text(renderRender(v)) },
      execute: async (args) => build("render", args),
    },
    {
      name: "cad_submit",
      description:
        "Export your module's solid as this case's STEP file. Call it once, when the gates pass. " +
        "It re-checks provenance and re-builds, so submitting a module that does not build fails here.",
      parameters: {
        path: { type: "string", required: true, description: "File holding the module, e.g. solution.py" },
      },
      output: {
        schema: { type: "object", additionalProperties: true },
        render: (_a, v) =>
          text(v?.ok ? `submitted: ${v.path} (${v.bytes} bytes)` : `SUBMIT FAILED in ${v?.stage ?? "?"}: ${v?.error ?? v?.report}`),
      },
      execute: async (args) => build("submit", args),
    },
  ];
}

export function apply(ctx, config = {}) {
  for (const definition of toolDefinitions(config)) {
    ctx.tools.register(definition);
  }

  // The discipline ships inside the package and is registered as a runtime skill,
  // so it reaches every session regardless of which agent preset it picked.
  try {
    const skillPath = join(pluginRoot, "skills", "cad-reconstruction", "SKILL.md");
    const raw = readFileSync(skillPath, "utf8");
    const front = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(raw);
    const meta = {};
    if (front) {
      for (const line of front[1].split(/\r?\n/)) {
        const index = line.indexOf(":");
        if (index > 0) meta[line.slice(0, index).trim()] = line.slice(index + 1).trim();
      }
    }
    const content = front ? raw.slice(front[0].length) : raw;
    const dispose = ctx.skills.register({
      name: meta.name || "cad-reconstruction",
      description: meta.description || "Constraint-guided CAD reconstruction discipline",
      content,
      // The registry requires a string `source` on the loaded definition; without
      // it the catalog lists the skill but every load fails with
      // `loaded skill "<name>" source must be a string`.
      source: meta.source || "runtime",
      invocation: { modelInvocable: true, userInvocable: true },
    });
    if (typeof dispose === "function") ctx.effect?.(() => dispose, "agentic-cad: skill");
  } catch (error) {
    console.warn(`[${PLUGIN_ID}] skill registration skipped: ${error?.message ?? error}`);
  }
}

export default { name, inject, apply };
