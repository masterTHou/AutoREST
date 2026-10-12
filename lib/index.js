// AutoREST DSH Plugin Entry
// Registers the autorest skill with DSH's skill system.

import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const skillPath = path.resolve(__dirname, '..', 'assets', 'skills', 'autorest');

/**
 * Activate the AutoREST plugin.
 */
export function activate(context) {
  if (context.skills?.register) {
    context.skills.register(skillPath);
  }
  console.log('[AutoREST] Plugin activated at', skillPath);
}

export function deactivate() {
  console.log('[AutoREST] Plugin deactivated');
}

export { skillPath };