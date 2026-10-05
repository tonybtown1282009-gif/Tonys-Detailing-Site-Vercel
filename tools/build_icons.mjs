// Build assets/lucide-<version>-subset.min.js: only the icons the pages use,
// exposed as the same global `lucide.createIcons()` the pages already call.
//
//   npm i lucide@1.23.0 esbuild      (in a scratch dir)
//   node tools/build_icons.mjs <repo-root>
//
// It scans every page for data-lucide="name", so re-run it after adding an icon.
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const root = path.resolve(process.argv[2] || ".");
const pascal = (n) => n.split("-").map((s) => s[0].toUpperCase() + s.slice(1)).join("");
// Names this lucide version renamed; each maps to the file that renders the
// same shape the old full bundle did for that name.
const FILE = { "alert-triangle": "triangle-alert", "check-circle": "circle-check-big", "help-circle": "circle-question-mark" };

const sources = fs.readdirSync(root).filter((f) => f.endsWith(".html")).map((f) => fs.readFileSync(path.join(root, f), "utf8"));
sources.push(fs.readFileSync(path.join(root, "app.py"), "utf8"));
const names = [...new Set(sources.join("\n").match(/data-lucide=\\?"[a-z0-9-]+/g).map((m) => m.split('"')[1]))].sort();

const lines = names.map((n) => `import ${pascal(n)} from "lucide/dist/esm/icons/${FILE[n] || n}.mjs";`);
lines.push('import { createIcons as c } from "lucide/dist/esm/lucide.mjs";');
lines.push(`const icons = { ${names.map(pascal).join(", ")} };`);
lines.push("export const createIcons = (o) => c({ icons, ...o });");
fs.writeFileSync("entry.mjs", lines.join("\n"));
execFileSync("npx", ["esbuild", "entry.mjs", "--bundle", "--minify", "--format=iife", "--global-name=lucide", "--legal-comments=none", `--outfile=${path.join(root, "assets/lucide-1.23.0-subset.min.js")}`], { stdio: "inherit" });
