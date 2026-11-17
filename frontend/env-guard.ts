// Build-time guard: Vite inlines every VITE_* variable into the public bundle,
// so a secret-looking VITE_* name is a configuration error, never a feature.
export const CLIENT_ENV_PREFIX = "VITE_";
const SECRETISH = /(KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE|AUTH)/i;

export function findUnsafeClientEnv(env: Record<string, string | undefined>): string[] {
  return Object.keys(env)
    .filter((name) => name.toUpperCase().startsWith(CLIENT_ENV_PREFIX))
    .filter((name) => SECRETISH.test(name.slice(CLIENT_ENV_PREFIX.length)))
    .sort();
}
