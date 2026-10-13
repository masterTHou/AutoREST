// AutoREST v3.0.0 — Cordis plugin with real Tool registration
// Registers 3 tools (detect REST, generate input, parse output) 
// plus a bundled Skill and system prompt guidance.
import { readFileSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import { platform, homedir } from "node:os";
import { existsSync, statSync } from "node:fs";
import { join } from "node:path";

export const name = "autorest";
export const inject = ["tools", "skills", "systemPrompt"];

// ============================================================================
// Tool 1: autorest_detect_rest — find the REST executable
// ============================================================================
async function toolDetectRest(_args, _exec) {
  const results = [];
  const locatorExe = platform() === "win32" ? "rest.exe" : "rest";

  // 1. Check conda environments
  const condaDirs = [
    join(homedir(), "anaconda3", "envs"),
    join(homedir(), "miniconda3", "envs"),
    join(homedir(), "miniforge3", "envs"),
    "C:\\ProgramData\\anaconda3\\envs",
    "C:\\ProgramData\\miniconda3\\envs",
    "/opt/anaconda3/envs",
    "/opt/miniconda3/envs",
  ];
  for (const envsDir of condaDirs) {
    try {
      if (!existsSync(envsDir)) continue;
      const { readdirSync: rd } = await import("node:fs");
      for (const env of rd(envsDir)) {
        const candidate = join(envsDir, env, "bin", locatorExe);
        const candidateWin = join(envsDir, env, "Library", "bin", locatorExe);
        for (const c of [candidate, candidateWin]) {
          if (existsSync(c) && statSync(c).isFile()) {
            try {
              const ver = execSync(`"${c}" --version 2>&1 || echo ""`, { encoding: "utf8", timeout: 5000 }).trim();
              results.push({ path: c, version: ver || "unknown", source: "conda", env });
            } catch (_) {
              results.push({ path: c, version: "detected (version unknown)", source: "conda", env });
            }
          }
        }
      }
    } catch (_) { /* env dir not readable */ }
  }

  // 2. Check system PATH
  try {
    const which = platform() === "win32" ? "where" : "which";
    const pathOut = execSync(`${which} ${locatorExe} 2>&1`, { encoding: "utf8", timeout: 5000 }).trim();
    if (pathOut && !pathOut.startsWith("INFO:") && !pathOut.includes("not found")) {
      const paths = pathOut.split(/\r?\n/).filter(p => p && existsSync(p.trim()));
      for (const p of paths) {
        if (!results.some(r => r.path === p.trim())) {
          try {
            const ver = execSync(`"${p.trim()}" --version 2>&1 || echo ""`, { encoding: "utf8", timeout: 5000 }).trim();
            results.push({ path: p.trim(), version: ver || "unknown", source: "path" });
          } catch (_) {
            results.push({ path: p.trim(), version: "detected (version unknown)", source: "path" });
          }
        }
      }
    }
  } catch (_) { /* not on PATH */ }

  // 3. Check current conda environment
  try {
    const condaPrefix = process.env.CONDA_PREFIX;
    if (condaPrefix) {
      for (const sub of ["bin", "Library/bin"]) {
        const c = join(condaPrefix, sub, locatorExe);
        if (existsSync(c) && statSync(c).isFile() && !results.some(r => r.path === c)) {
          try {
            const ver = execSync(`"${c}" --version 2>&1 || echo ""`, { encoding: "utf8", timeout: 5000 }).trim();
            results.push({ path: c, version: ver || "unknown", source: "active_conda_env" });
          } catch (_) {
            results.push({ path: c, version: "detected (version unknown)", source: "active_conda_env" });
          }
        }
      }
    }
  } catch (_) { /* no CONDA_PREFIX */ }

  const best = results.length > 0 ? results[0] : null;
  return {
    found: results.length > 0,
    count: results.length,
    best_path: best?.path ?? null,
    best_version: best?.version ?? null,
    best_source: best?.source ?? null,
    all: results,
    recommendation: best
      ? `REST found at: ${best.path}\nSource: ${best.source}\nUse: conda activate ${best.env || 'rest'} && rest -i input.in > output.out`
      : "REST not found. Install via conda: conda create -n rest -c restgroup rest\nThen: conda activate rest",
  };
}

// ============================================================================
// Tool 2: autorest_generate_input — generate a REST .in file
// ============================================================================
async function toolGenerateInput(args, _exec) {
  const { system_name, geometry, geometry_unit, functional, basis, charge, spin,
          job_type, empirical_dispersion, num_threads, auxbas_path,
          bse_spin, n_roots } = args;

  const disp = (empirical_dispersion && !["XYG3","XYG7","XYGJOS","xDH-PBE0","R-xDH7","scsRPA","RPA@PBE","RPA@B3LYP"].includes(functional))
    ? `empirical_dispersion = "${empirical_dispersion}"` : "";

  const spinPol = spin === undefined || spin === 1 ? "false" : "true";
  const threads = num_threads || 4;
  const job = job_type || "energy";
  const aux = auxbas_path ? `auxbas_path = "${auxbas_path}"` : "";

  let card = `[ctrl]\nnum_threads = ${threads}\nprint_level = 1\njob_type = "${job}"\nxc = "${functional}"\n`;
  if (disp) card += `${disp}\n`;
  card += `basis_path = "${basis}"\n`;
  if (aux) card += `${aux}\n`;
  card += `eri_type = "ri-v"\ncharge = ${charge ?? 0}\nspin = ${spin ?? 1}\nspin_polarization = ${spinPol}\n`;

  if (job_type === "opt") {
    card += `opt_engine = "geometric-pyo3"\n`;
  }

  if (bse_spin) {
    card += `\n[quasiparticle_methods]\ngw_or_bse = "bse"\ngw_scheme = "extrapolated"\n`;
    card += `use_low_rank_contour = true\nbse_spin = "${bse_spin}"\nbse_tda = true\n`;
    card += `bse_davidson_solver = true\ndavidson_target_excitations = ${n_roots || 5}\n`;
    card += `davidson_maximum_subspace_size = 50\ndavidson_restart_dimensions = 10\n`;
  }

  card += `\n[geom]\nname = "${system_name || "MOLECULE"}"\nunit = "${geometry_unit || "angstrom"}"\nposition = """\n`;
  for (const line of (geometry || "").trim().split("\n")) {
    card += line.trim() + "\n";
  }
  card += '"""\n';

  return { card, filename: `${(system_name || "molecule").replace(/\s+/g, "_")}_${job}.in` };
}

// ============================================================================
// Tool 3: autorest_parse_output — parse a REST output file
// ============================================================================
async function toolParseOutput(args, _exec) {
  const { output_path } = args;
  if (!output_path) return { error: "output_path is required" };

  let text;
  try {
    const raw = await import("node:fs/promises").then(fs => fs.readFile(output_path));
    // Detect BOM
    if (raw[0] === 0xFF && raw[1] === 0xFE) text = raw.toString("utf16le");
    else if (raw[0] === 0xFE && raw[1] === 0xFF) text = raw.toString("utf16be");
    else text = raw.toString("utf8");
  } catch (e) {
    return { error: `Cannot read file: ${e.message}` };
  }

  const result = { scf_converged: false, scf_energy: null, scf_cycles: 0,
    mission_accomplished: false, total_time_s: null,
    gw_finished: false, qp_gap_ev: null, bse_spin: null, states: [] };

  // SCF convergence
  const scfMatch = text.match(/SCF\s+is\s+converged\s+after\s+(\d+)\s+iterations/i);
  if (scfMatch) { result.scf_converged = true; result.scf_cycles = parseInt(scfMatch[1]); }

  // SCF energy (use definitive summary line, not initial guess)
  const scfFinal = text.match(/The\s+SCF\s+energy\s*:\s*([+-]?\d+\.\d+)\s*Ha/i);
  if (scfFinal) result.scf_energy = parseFloat(scfFinal[1]);
  else {
    const energyLines = [...text.matchAll(/Energy:\s+([+-]?\d+\.\d+)\s+Ha/gi)];
    if (energyLines.length > 0) result.scf_energy = parseFloat(energyLines[energyLines.length - 1][1]);
  }

  // Mission
  result.mission_accomplished = /Mission\s+accomplished/i.test(text);

  // GW
  result.gw_finished = /One\s+round\s+of\s+GW|Quasiparticle\s+Energies\s+from\s+GW/i.test(text);

  // QP gap
  const qpLines = [...text.matchAll(/\(calculated\)\s*QP\s+Energy\s+of\s+Orbital\s+#(\d+):\s*([+-]?\d+\.\d+)/gi)];
  if (qpLines.length > 0) {
    const fermiMatch = text.match(/-{3,}\s*Fermi\s+Surface\s*-{3,}/i);
    if (fermiMatch) {
      const sepLine = text.slice(0, fermiMatch.index).split("\n").length;
      const occ = qpLines.filter(m => text.slice(0, text.indexOf(m[0])).split("\n").length < sepLine);
      const virt = qpLines.filter(m => text.slice(0, text.indexOf(m[0])).split("\n").length > sepLine);
      if (occ.length > 0 && virt.length > 0) {
        const homoE = Math.max(...occ.map(m => parseFloat(m[2])));
        const lumoE = Math.min(...virt.map(m => parseFloat(m[2])));
        result.qp_gap_ev = (lumoE - homoE) * 27.2113845;
      }
    }
  }

  // BSE spin
  const bseMatch = text.match(/BSE\s+Type\s*:\s*(singlet|triplet)/i);
  if (bseMatch) result.bse_spin = bseMatch[1].toLowerCase();

  // BSE states
  const windowMatch = text.match(/(\d+)\s+excitations?\s+within\s+the\s+window/i);
  if (windowMatch) {
    const body = text.slice(text.indexOf(windowMatch[0]) + windowMatch[0].length);
    const states = [];
    const stateRegex = /#(\d+)\s+Excitation\s+energy\s*=\s*([+-]?\d+(?:\.\d+)?)/gi;
    const oscRegex = /Oscillator\s+Strength\s*:\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/gi;
    let sm;
    while ((sm = stateRegex.exec(body)) !== null) {
      const eHa = parseFloat(sm[2]);
      states.push({ index: parseInt(sm[1]), energy_ha: eHa, energy_ev: eHa * 27.2113845,
        wavelength_nm: eHa > 0 ? 1239.84 / (eHa * 27.2113845) : 0, oscillator_strength: 0 });
    }
    let om; let si = 0;
    while ((om = oscRegex.exec(body)) !== null && si < states.length) {
      states[si++].oscillator_strength = parseFloat(om[1]);
    }
    result.states = states;
  }

  // Timing
  const timeMatch = text.match(/Overall\s*\|:\s*([\d.]+)\s*s\s+for\s+the\s+whole\s+job/i);
  if (timeMatch) result.total_time_s = parseFloat(timeMatch[1]);

  return result;
}

// ============================================================================
// System prompt guidance
// ============================================================================
const AUTOREST_PROMPT = [
  "AutoREST is a quantum chemistry assistant that generates REST electronic-structure input cards as .in files (TOML format with [ctrl] and [geom] blocks).",
  "Before suggesting any calculation, ALWAYS call the autorest_detect_rest tool first to check whether REST is installed.",
  "If REST is found: tell the user the path and version, and offer to run calculations (conda activate <env> && rest -i file.in > file.out).",
  "If REST is NOT found: generate .in files only. Tell the user: 'REST not detected. Install with: conda create -n rest -c restgroup rest'. Also tell them they can run: rest -i filename.in > filename.out once installed.",
  "Use the bundled 'autorest' Skill for the interactive Q&A workflow.",
  "Use autorest_generate_input tool to generate valid REST .in cards from confirmed parameters.",
  "Use autorest_parse_output tool to analyze REST output files the user provides.",
  "REST input files use .in extension with TOML content inside, not JSON.",
  "empirical_dispersion is a separate keyword - never appended to xc.",
  "For triplet BSE: keep spin=1 (closed-shell reference) and set bse_spin='triplet'. Never change spin to 3.",
].join(" ");

// ============================================================================
// Skill registration (unchanged from v2)
// ============================================================================
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

// ============================================================================
// Cordis plugin entry point
// ============================================================================
export function apply(ctx, _config) {
  // 1. Register tools
  ctx.effect(() => {
    const d1 = ctx.tools.register({
      name: "autorest_detect_rest",
      description: "Detect REST electronic-structure program on this computer. Checks conda environments, system PATH, and active conda env. Returns whether REST is found, its path, version, and a usage recommendation. Call this FIRST before suggesting any calculation.",
      parameters: { type: "object", properties: {}, required: [] },
      execute: toolDetectRest,
    });
    const d2 = ctx.tools.register({
      name: "autorest_generate_input",
      description: "Generate a valid REST .in input file from confirmed parameters. Requires system_name, geometry (XYZ format), geometry_unit, functional, basis, charge, spin. Optional: job_type (default energy), empirical_dispersion, num_threads, auxbas_path, bse_spin, n_roots. Returns the TOML card text and suggested filename.",
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
          job_type: { type: "string", description: "energy, opt, or force" },
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
      description: "Parse a REST calculation output file. Extracts SCF energy/convergence, GW quasiparticle gap, BSE excitation energies/oscillator strengths, Davidson diagnostics, and timing. Handles UTF-8 and UTF-16 encodings.",
      parameters: {
        type: "object",
        properties: { output_path: { type: "string", description: "Path to the REST .out file" } },
        required: ["output_path"],
      },
      execute: toolParseOutput,
    });
    return () => { d1(); d2(); d3(); };
  });

  // 2. Register system prompt
  ctx.effect(() =>
    ctx.systemPrompt.section({ name: "autorest:guidance", order: 90, text: AUTOREST_PROMPT })
  );

  // 3. Register the bundled skill
  ctx.effect(() => {
    const skillFile = fileURLToPath(new URL("../../assets/skills/autorest/SKILL.md", import.meta.url));
    return ctx.inject(["skills"], (child) => {
      child.effect(() => registerSkillProvider(child.skills, skillFile));
    });
  });
}