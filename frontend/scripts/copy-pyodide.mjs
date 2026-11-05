// Copies the Pyodide runtime (Python in WebAssembly) into public/ so the app can
// run Python even when the CDN is unreachable. Runs before dev/build.
import { cpSync, existsSync, mkdirSync, readdirSync } from "node:fs";

const src = "node_modules/pyodide";
const dest = "public/pyodide";
if (!existsSync(src)) {
  console.error("pyodide is not installed; run npm install");
  process.exit(1);
}
mkdirSync(dest, { recursive: true });
for (const f of readdirSync(src)) {
  if (/\.(mjs|js|wasm|zip|json)$/.test(f) && !f.endsWith(".map") && f !== "package.json") {
    cpSync(`${src}/${f}`, `${dest}/${f}`);
  }
}
console.log("Pyodide copied to", dest);
