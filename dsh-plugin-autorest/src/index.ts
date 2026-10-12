/**
 * AutoREST DSH plugin: Cordis function plugin that bundles a REST quantum
 * chemistry Skill into DeepSeek Harness. No backend service, no API — just
 * the bundled Skill instructions plus system prompt guidance.
 */
import { readFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'

/** Cordis function-plugin name. */
export const name = 'autorest'

/** Services the plugin requires before its `apply` runs. */
export const inject = ['skills', 'systemPrompt'] as const

/** Deployment-facing configuration (kept minimal — no backend). */
export interface Config {}

/** System prompt guidance injected into every conversation. */
const AUTOREST_PROMPT = [
  "AutoREST is a quantum chemistry assistant that generates REST electronic-structure input files (TOML format with [ctrl] and [geom] blocks).",
  "When a user asks to calculate a molecule, use the bundled 'autorest' Skill for guidance. The Skill defines a mandatory 3-step interactive workflow:",
  "Panel 1: task type (energy/opt/freq/TDDFT/GWBSE) + molecule source (user-provided or AI-generated) + charge/spin.",
  "Panel 2: method selection (B3LYP-D3BJ/def2-SVP recommended for organic molecules; PBE0-D3BJ/def2-TZVP for quantitative; XYG3/def2-QZVPP for benchmark) + resource budget.",
  "Panel 3: summary confirmation then generate the REST TOML input card.",
  "Never generate an input card without asking the user first. Always use ask_user_question panels.",
  "REST input cards are TOML format, not JSON. Required blocks: [ctrl] and [geom]. charge and spin go in [ctrl].",
  "empirical_dispersion is a separate keyword — never appended to xc. Double-hybrid/RPA methods must NOT have empirical dispersion.",
  "For triplet BSE: keep spin=1 (closed-shell reference) and set bse_spin='triplet'. Never change spin to 3 for triplet excitation.",
  "Reference files: references/rest_readme.txt (full REST keyword catalog), references/rest_guide.md (methods and templates), references/gwbse_guide.md (GW-BSE rules and regression data).",
].join(' ')

/**
 * Register the bundled Skill through DSH's Skill service.
 * Mirrors AIFS's `registerPlanningSkill` — same pattern.
 */
function registerBundledSkill(ctx: Context): () => void {
  return ctx.inject(['skills'], (child) => {
    const skillFile = fileURLToPath(new URL('../../skills/autorest/SKILL.md', import.meta.url))
    child.effect(() => {
      return registerSkillProvider(child.skills, skillFile)
    })
  })
}

/**
 * Register a single bundled skill with the DSH Skill service.
 * Parses the YAML frontmatter (name, description) and serves the
 * Markdown body as skill content. Resource base points to the skill
 * directory so relative references/scripts resolve.
 */
function registerSkillProvider(
  service: { registerProvider: (create: () => {
    name: string
    list: () => Promise<Array<{
      name: string; description: string
      invocation: { modelInvocable: boolean; userInvocable: boolean }
      provider: string; source: string; rank: number
      resourceBase: { kind: string; path: string }
      locator: string
    }>>
    get: (candidate: { name: string; locator: string }) => Promise<{
      name: string; description: string; content: string
      invocation: { modelInvocable: boolean; userInvocable: boolean }
      provider: string; source: string
      resourceBase: { kind: string; path: string }
    }>
  }) => () => void },
  path: string,
): () => void {
  const raw = readFileSync(path, 'utf8')
  const match = /^---\r?\nname: ([^\r\n]+)\r?\ndescription: ([^\r\n]+)\r?\n---\r?\n([\s\S]*)$/.exec(raw)
  if (!match) throw new Error('Invalid bundled AutoREST Skill metadata')
  const skillDir = dirname(path)
  const candidate = {
    name: match[1]!,
    description: match[2]!,
    invocation: { modelInvocable: true, userInvocable: true },
    provider: 'autorest',
    source: 'bundled' as const,
    rank: 600,
    resourceBase: { kind: 'directory' as const, path: skillDir },
    locator: path,
  }
  return service.registerProvider(() => ({
    name: 'autorest',
    list: async () => [candidate],
    get: async () => {
      const content = raw.slice(match[0].length).trimStart()
      return {
        name: candidate.name,
        description: candidate.description,
        content,
        invocation: candidate.invocation,
        provider: candidate.provider,
        source: candidate.source,
        resourceBase: candidate.resourceBase,
      }
    },
  }))
}

export function apply(ctx: Context, _config: Config): void {
  // Register system prompt guidance
  ctx.effect(() =>
    ctx.systemPrompt.section({ name: 'autorest:guidance', order: 90, text: AUTOREST_PROMPT }),
  )
  // Register the bundled skill
  ctx.effect(() => registerBundledSkill(ctx))
}