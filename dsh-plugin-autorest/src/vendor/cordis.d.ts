/**
 * Ambient mirror of the `@deepseek-ai/cordis` subset this plugin uses.
 *
 * The plugin is developed outside the deepseek-harness workspace, where the
 * real package is not installable. This declaration is type-only and matches
 * the public API surface used here; when the plugin is mounted into the
 * harness workspace the real package resolves and this mirror can be deleted.
 */
declare module '@deepseek-ai/cordis' {
  export interface SkillService {
    registerProvider(create: () => {
      name: string
      list: () => Promise<Array<{
        name: string
        description: string
        invocation: { modelInvocable: boolean; userInvocable: boolean }
        provider: string
        source: 'bundled'
        rank: number
        resourceBase: { kind: 'directory'; path: string }
        locator: string
      }>>
      get: (candidate: {
        name: string
        locator: string
      }) => Promise<{
        name: string
        description: string
        content: string
        invocation: { modelInvocable: boolean; userInvocable: boolean }
        provider: string
        source: 'bundled'
        resourceBase: { kind: 'directory'; path: string }
      }>
    }): () => void
  }

  export interface SystemPrompt {
    section(section: {
      name: string
      order: number
      text: string
    }): () => void
  }

  export interface Context {
    skills: SkillService
    systemPrompt: SystemPrompt
    inject(services: string[], callback: (child: Context) => void): unknown
    effect(fn: () => (() => void) | void): void
  }
}