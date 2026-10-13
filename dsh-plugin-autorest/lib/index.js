// AutoREST DSH Plugin — bundled skill-only Cordis plugin
// No backend, no API, just registers the autorest Skill with DSH.
import { readFileSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

export const name = "autorest";
export const inject = ["skills", "systemPrompt"];

const AUTOREST_PROMPT = [
  "AutoREST is a quantum chemistry assistant that generates REST electronic-structure input files as .in files (TOML format inside with [ctrl] and [geom] blocks).",
  "Run REST with: conda activate rest && rest -i filename.in > filename.out",
  "When a user asks to calculate a molecule, use the bundled 'autorest' Skill for guidance. The Skill defines a mandatory 3-step interactive workflow:",
  "Panel 1: task type (energy/opt/freq/TDDFT/GWBSE) + molecule source (user-provided or AI-generated) + charge/spin.",
  "Panel 2: method selection (B3LYP-D3BJ/def2-SVP recommended for organic molecules; PBE0-D3BJ/def2-TZVP for quantitative; XYG3/def2-QZVPP for benchmark) + resource budget.",
  "Panel 3: summary confirmation then generate the .in REST input file (TOML format).",
  "Never generate an input card without asking the user first. Always use ask_user_question panels.",
  "REST input files use .in extension with TOML content inside, not JSON. Required blocks: [ctrl] and [geom]. charge and spin go in [ctrl].",
  "empirical_dispersion is a separate keyword - never appended to xc. Double-hybrid/RPA methods must NOT have empirical dispersion.",
  "For triplet BSE: keep spin=1 (closed-shell reference) and set bse_spin='triplet'. Never change spin to 3 for triplet excitation.",
  "Reference files: references/rest_readme.txt (full REST keyword catalog), references/rest_guide.md (methods and templates), references/gwbse_guide.md (GW-BSE rules and regression data).",
].join(" ");

const _AUTOREST_PROMPT_TEXT = AUTOREST_PROMPT;

function registerSkillProvider(service, path) {
  const raw = readFileSync(path, "utf8");
  const match = /^---\r?\nname: ([^\r\n]+)\r?\ndescription: ([^\r\n]+)\r?\n---\r?\n([\s\S]*)$/.exec(raw);
  if (!match) throw new Error("Invalid bundled AutoREST Skill metadata");
  const skillDir = dirname(path);
  const candidate = {
    name: match[1],
    description: match[2],
    invocation: { modelInvocable: true, userInvocable: true },
    provider: "autorest",
    source: "bundled",
    rank: 600,
    resourceBase: { kind: "directory", path: skillDir },
    locator: path,
  };
  return service.registerProvider(() => ({
    name: "autorest",
    list: async () => [candidate],
    get: async () => {
      const content = raw.slice(match[0].length).trimStart();
      return {
        name: candidate.name,
        description: candidate.description,
        content,
        invocation: candidate.invocation,
        provider: candidate.provider,
        source: candidate.source,
        resourceBase: candidate.resourceBase,
      };
    },
  }));
}

export function apply(ctx, _config) {
  // 1. Register system prompt guidance
  ctx.effect(() =>
    ctx.systemPrompt.section({ name: "autorest:guidance", order: 90, text: _AUTOREST_PROMPT_TEXT })
  );
  // 2. Register the bundled skill
  ctx.effect(() => {
    const skillFile = fileURLToPath(new URL("../../assets/skills/autorest/SKILL.md", import.meta.url));
    return ctx.inject(["skills"], (child) => {
      child.effect(() => registerSkillProvider(child.skills, skillFile));
    });
  });
}