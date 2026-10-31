// Writes the backend FastAPI OpenAPI schema to openapi/backend-openapi.json
// with sorted keys, so the committed snapshot only changes when the
// contract changes. Uses the backend's own Python environment:
//
//   npm run export:openapi
//   STEEL_COMPASS_PYTHON=/path/to/python npm run export:openapi

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backend = resolve(root, "../backend");
const venvPython = resolve(backend, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const python = process.env.STEEL_COMPASS_PYTHON || (existsSync(venvPython) ? venvPython : "python");

const code = "import json, sys; from app.main import app; sys.stdout.write(json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True, indent=2))";
const output = execFileSync(python, ["-c", code], { cwd: backend, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
const target = resolve(root, "openapi/backend-openapi.json");
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, `${output}\n`);
console.log(`Wrote ${target}`);
