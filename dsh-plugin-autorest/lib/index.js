// AutoREST v4 — Cordis plugin with real Tool registration + JSON bridge
// Registers 3 tools (detect_rest, generate_input, parse_output)
// Uses DSH shell seam (ctx.shell) to invoke Python bridge — no raw child_process.
import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

export const name = "autorest";
export const inject = ["tools", "skills", "systemPrompt", "shell"];

// ══════════════════════════════════════════════════════════════════
// Configuration
// ══════════════════════════════════════════════════════════════════
const DEFAULTS = {
  pythonExecutable: null,          // auto-detect from CONDA_PREFIX / PATH
  bridgeTimeoutMs: 30000,
  maxParseBytes: 4 * 1024 * 1024, // 4 MB
  skillEnabled: true,
  guidanceMode: "adaptive",       // "adaptive" | "guided"
};

function resolvePython() {
  const exe = DEFAULTS.pythonExecutable;
  if (exe && existsSync(exe)) return exe;
  // Try CONDA_PREFIX
  const prefix = process.env.CONDA_PREFIX;
  if (prefix) {
    const candidates = [
      resolve(prefix, "bin", "python3"),
      resolve(prefix, "bin", "python"),
      resolve(prefix, "Library", "bin", "python.exe"),
    ];
    for (const c of candidates) if (existsSync(c)) return c;
  }
  // Fallback
  return process.platform === "win32" ? "python" : "python3";
}

const BRIDGE_SCRIPT = fileURLToPath(new URL("../../vendor/python/autorest/dsh_bridge.py", import.meta.url));

// ══════════════════════════════════════════════════════════════════
// Bridge invoker — uses ctx.shell (DSH shell seam)
// ══════════════════════════════════════════════════════════════════
async function invokeBridge(ctx, action, payload, signal) {
  const python = resolvePython();
  const stdin = JSON.stringify({ protocol: 1, action, payload });

  const result = await ctx.shell.execute({
    command: python,
    args: [BRIDGE_SCRIPT],
    stdin,
    workdir: resolve(dirname(BRIDGE_SCRIPT), "..", "..", ".."),
    timeoutMs: DEFAULTS.bridgeTimeoutMs,
    signal,
    maxStdoutBytes: DEFAULTS.maxParseBytes + 65536,
  });

  if (result.timedOut) {
    return { ok: false, code: "TIMEOUT", message: "Bridge timed out.", hint: "Try again or increase timeout." };
  }
  if (result.exitCode !== 0) {
    return { ok: false, code: "INTERNAL_ERROR",
      message: `Python bridge exited with code ${result.exitCode}.`,
      hint: "Check that Python and AutoREST dependencies are installed." };
  }
  try {
    return JSON.parse(result.stdout || "{}");
  } catch (_) {
    return { ok: false, code: "BRIDGE_PROTOCOL_ERROR",
      message: "Bridge returned invalid JSON.", hint: "This may indicate a version mismatch." };
  }
}

// ══════════════════════════════════════════════════════════════════
// Tool: autorest_detect_rest
// ══════════════════════════════════════════════════════════════════
async function toolDetectRest(args, execCtx) {
  const resp = await invokeBridge(execCtx.ctx, "detect", {}, execCtx.signal);
  return renderDetect(resp);
}

function renderDetect(resp) {
  const d = resp.data || {};
  const found = d.rest_found;
  if (resp.ok && found) {
    return {
      ok: true,
      rest_available: true,
      rest_path: d.rest_executable,
      rest_version: d.rest_version,
      rest_source: d.rest_source,
      conda_env: d.conda_env,
      python_version: d.python_version,
      bridge_protocol: d.bridge_protocol_version,
      capabilities: d.capabilities,
      warnings: d.warnings,
      summary: `REST found at ${d.rest_executable} (${d.rest_source || 'unknown'}). Python ${d.python_version}. AutoREST bridge v${d.bridge_protocol_version}.`,
      next_action: d.next_action,
    };
  }
  return {
    ok: true,
    rest_available: false,
    python_version: d.python_version,
    bridge_protocol: d.bridge_protocol_version,
    capabilities: d.capabilities || [],
    warnings: d.warnings || [],
    summary: "REST not detected. AutoREST can still generate .in input files. Install REST via: conda create -n rest -c restgroup rest",
    next_action: d.next_action || "Install REST with conda.",
  };
}

// ══════════════════════════════════════════════════════════════════
// Tool: autorest_generate_input
// ══════════════════════════════════════════════════════════════════
async function toolGenerateInput(args, execCtx) {
  const resp = await invokeBridge(execCtx.ctx, "generate_input", args, execCtx.signal);
  if (!resp.ok) return resp;
  const d = resp.data || {};
  return {
    ok: true,
    toml: d.toml,
    suggested_filename: d.suggested_filename,
    task_summary: d.task_summary,
    warnings: d.warnings || [],
    summary: `Input card generated: ${d.suggested_filename} (${d.task_summary?.functional}/${d.task_summary?.basis}, ${d.task_summary?.job_type})`,
    hint: "Save this card as a .in file, then run: conda activate rest && rest -i filename.in > filename.out",
  };
}

// ══════════════════════════════════════════════════════════════════
// Tool: autorest_parse_output
// ══════════════════════════════════════════════════════════════════
function resolveWorkspacePath(rawPath, execCtx) {
  const cwd = execCtx.ctx?.cwd || process.cwd();
  const resolved = resolve(cwd, rawPath);
  // containment: reject ../
  if (!resolved.startsWith(cwd + sep) && resolved !== cwd) {
    throw Object.assign(new Error("Path is outside workspace"), { code: "PATH_OUTSIDE_WORKSPACE" });
  }
  return resolved;
}

async function toolParseOutput(args, execCtx) {
  const rawPath = args.output_path;
  if (!rawPath) return { ok: false, code: "INVALID_ARGUMENT", message: "output_path is required." };

  let resolvedPath;
  try {
    resolvedPath = resolveWorkspacePath(rawPath, execCtx);
  } catch (e) {
    return { ok: false, code: e.code || "PATH_OUTSIDE_WORKSPACE", message: e.message };
  }

  // Read file via DSH filesystem seam
  let text;
  try {
    const raw = await execCtx.ctx.fs?.readFile?.(resolvedPath);
    if (!raw) {
      // fallback: direct read (sandboxed)
      text = readFileSync(resolvedPath, { encoding: "utf8" });
    } else {
      // detect BOM for UTF-16
      if (raw[0] === 0xFF && raw[1] === 0xFE) text = Buffer.from(raw).toString("utf16le");
      else if (raw[0] === 0xFE && raw[1] === 0xFF) text = Buffer.from(raw).toString("utf16be");
      else text = Buffer.from(raw).toString("utf8");
    }
  } catch (e) {
    return { ok: false, code: "FILE_NOT_FOUND", message: `Cannot read ${rawPath}` };
  }

  if (text.length > DEFAULTS.maxParseBytes) {
    return { ok: false, code: "FILE_TOO_LARGE", message: `File exceeds ${DEFAULTS.maxParseBytes} bytes.` };
  }

  const resp = await invokeBridge(execCtx.ctx, "parse_output", { text }, execCtx.signal);
  if (!resp.ok) return resp;

  const d = resp.data || {};
  return {
    ok: true,
    scf_energy: d.scf_energy,
    scf_converged: d.scf_converged,
    scf_cycles: d.scf_cycles,
    total_energy: d.total_energy,
    dipole: d.dipole,
    frequencies: d.frequencies,
    imaginary_frequencies: d.imaginary_frequencies,
    zpe: d.zpe,
    forces: d.forces,
    optimized_geometry: d.optimized_geometry,
    optimization_converged: d.optimization_converged,
    mission_accomplished: d.mission_accomplished,
    wall_time_s: d.wall_time_s,
    bse_states: d.bse_states,
    warnings: d.warnings,
    qa_checks: d.qa_checks,
    summary: `SCF ${d.scf_converged ? 'converged' : 'NOT converged'}, energy=${d.scf_energy ?? 'N/A'} Ha. ${d.mission_accomplished ? 'Mission accomplished.' : ''}`,
  };
}

// ══════════════════════════════════════════════════════════════════
// Adaptive system prompt
// ══════════════════════════════════════════════════════════════════
const AUTOREST_PROMPT = [
  "AutoREST is a quantum chemistry plugin. It registers three tools:",
  "  autorest_detect_rest — checks whether REST is installed",
  "  autorest_generate_input — generates .in input cards",
  "  autorest_parse_output — parses REST output files",
  "When a user asks to calculate a molecule, first call autorest_detect_rest.",
  "If the user already specified method/basis/charge/spin, do NOT ask again — go directly to generation.",
  "If information is missing, ask ONLY the missing pieces, using ask_user_question to batch independent questions.",
  "REST .in files use TOML format (NOT JSON). charge and spin go in [ctrl], not [geom].",
  "empirical_dispersion is a separate keyword. Double-hybrid/RPA must NOT have dispersion.",
  "Triplet BSE: keep spin=1 and set bse_spin='triplet'. Never change spin to 3.",
  "Detailed knowledge lives in the bundled 'autorest' Skill — load it with skill('autorest') when needed.",
].join(" ");

// ══════════════════════════════════════════════════════════════════
// Skill registration
// ══════════════════════════════════════════════════════════════════
function registerSkillProvider(service, path) {
  const raw = readFileSync(path, "utf8");
  const match = /^---\r?\nname: ([^\r\n]+)\r?\ndescription: ([^\r\n]+)\r?\n---\r?\n([\s\S]*)$/.exec(raw);
  if (!match) throw new Error("Invalid bundled AutoREST Skill metadata");
  const skillDir = dirname(path);
  const candidate = {
    name: match[1], description: match[2],
    invocation: { modelInvocable: true, userInvocable: true },
    provider: "autorest", source: "bundled", rank: 600,
    resourceBase: { kind: "directory", path: skillDir }, locator: path,
  };
  return service.registerProvider(() => ({
    name: "autorest",
    list: async () => [candidate],
    get: async () => {
      const content = raw.slice(match[0].length).trimStart();
      return { name: candidate.name, description: candidate.description, content,
        invocation: candidate.invocation, provider: candidate.provider,
        source: candidate.source, resourceBase: candidate.resourceBase };
    },
  }));
}

// ══════════════════════════════════════════════════════════════════
// Cordis entry point
// ══════════════════════════════════════════════════════════════════
export function apply(ctx, _config) {
  // 1. Register three tools
  ctx.effect(() => {
    const d1 = ctx.tools.register({
      name: "autorest_detect_rest",
      description: "Detect REST electronic-structure program on this computer. Checks conda environments and system PATH. Returns whether REST is found, its path, version, and a usage recommendation. Always call this first when a user asks about REST calculations.",
      parameters: { type: "object", properties: {}, required: [] },
      execute: toolDetectRest,
    });
    const d2 = ctx.tools.register({
      name: "autorest_generate_input",
      description: "Generate a valid REST .in input file from confirmed parameters. Requires system_name, geometry (XYZ), geometry_unit (angstrom/bohr), functional, basis, charge, spin. Optional: job_type (energy/opt/force/frequency), empirical_dispersion (d3/d3bj/d4), num_threads, auxbas_path, bse_spin (singlet/triplet), n_roots.",
      parameters: {
        type: "object",
        properties: {
          system_name: { type: "string", description: "Molecular system name" },
          geometry: { type: "string", description: "XYZ geometry, one atom per line: Element x y z" },
          geometry_unit: { type: "string", description: "angstrom or bohr", default: "angstrom" },
          functional: { type: "string", description: "DFT functional e.g. b3lyp, pbe0, scan" },
          basis: { type: "string", description: "Basis set e.g. def2-SVP, cc-pVDZ" },
          charge: { type: "number", description: "Net molecular charge" },
          spin: { type: "number", description: "Spin multiplicity 2S+1" },
          job_type: { type: "string", description: "energy, opt, force, or frequency" },
          empirical_dispersion: { type: "string", description: "d3, d3bj, or d4" },
          num_threads: { type: "number", description: "CPU thread count" },
          auxbas_path: { type: "string", description: "Auxiliary basis set" },
          bse_spin: { type: "string", description: "For GW-BSE: singlet or triplet" },
          n_roots: { type: "number", description: "Number of BSE excitation roots" },
        },
        required: ["system_name", "geometry", "functional", "basis", "charge", "spin"],
      },
      execute: toolGenerateInput,
    });
    const d3 = ctx.tools.register({
      name: "autorest_parse_output",
      description: "Parse a REST calculation output file. Extracts SCF energy/convergence, GW quasiparticle gap, BSE excitation energies/oscillator strengths, and scientific QA checks. Handles UTF-8 and UTF-16 encodings.",
      parameters: {
        type: "object",
        properties: { output_path: { type: "string", description: "Workspace-relative path to the REST .out file" } },
        required: ["output_path"],
      },
      execute: toolParseOutput,
    });
    return () => { d1(); d2(); d3(); };
  });

  // 2. System prompt
  ctx.effect(() =>
    ctx.systemPrompt.section({ name: "autorest:guidance", order: 90, text: AUTOREST_PROMPT })
  );

  // 3. Bundled Skill (self-contained within plugin)
  ctx.effect(() => {
    const skillFile = fileURLToPath(new URL("../resources/skill/SKILL.md", import.meta.url));
    return ctx.inject(["skills"], (child) => {
      child.effect(() => registerSkillProvider(child.skills, skillFile));
    });
  });
}