// Scan a built bundle for secrets. Exits 1 on any hit or if the bundle is missing.
// Prints only file names and rule labels, never the matched value.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

const root = resolve(process.argv[2] ?? "dist");

const RULES = [
  { label: "Google API key pattern", re: /AIza[0-9A-Za-z_-]{35}/ },
  { label: "Anthropic key pattern", re: /sk-ant-[0-9A-Za-z_-]{20,}/ },
  { label: "OpenAI-style key pattern", re: /\bsk-[0-9A-Za-z]{32,}/ },
  { label: "Private key block", re: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
];

// Exact values of server-only secrets present in this process (e.g. a sentinel in CI).
const SECRET_ENV_NAMES = ["YOUTUBE_API_KEY", "SECRET_SENTINEL", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"];
const literals = SECRET_ENV_NAMES.flatMap((name) => {
  const value = process.env[name];
  return value && value.trim().length >= 8 ? [{ label: `value of ${name}`, value }] : [];
});

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

let files;
try {
  files = walk(root);
} catch {
  console.error(`scan-bundle: bundle folder not found: ${root}`);
  process.exit(1);
}
if (files.length === 0) {
  console.error(`scan-bundle: bundle folder is empty: ${root}`);
  process.exit(1);
}

const hits = [];
for (const file of files) {
  const text = readFileSync(file, "latin1");
  for (const rule of RULES) if (rule.re.test(text)) hits.push(`${relative(root, file)}: ${rule.label}`);
  for (const lit of literals) if (text.includes(lit.value)) hits.push(`${relative(root, file)}: ${lit.label}`);
}

if (hits.length > 0) {
  console.error(`scan-bundle: FAILED, ${hits.length} finding(s):`);
  for (const hit of hits) console.error(`  ${hit}`);
  process.exit(1);
}
console.log(
  `scan-bundle: passed. ${files.length} file(s), ${RULES.length} patterns, ` +
    `${literals.length} env value(s) checked (${literals.map((l) => l.label).join(", ") || "none set"}).`,
);
