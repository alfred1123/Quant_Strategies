#!/usr/bin/env node
/**
 * Parse every ```mermaid block in the docs and fail on the first bad one.
 *
 * A malformed diagram fails *silently* on the published site: MkDocs emits the
 * block as `<pre class="mermaid">` regardless, mermaid-init.js flattens it to
 * raw text, and mermaid.run() then throws in the browser — leaving the source
 * on screen as if it were a code block. Nothing in `mkdocs build` notices,
 * which is how two broken diagrams sat in the wiki unnoticed.
 *
 * Parsing the raw fence is faithful to what the browser parses. MkDocs escapes
 * the block into HTML entities (`--&gt;`), but mermaid-init.js reads it back via
 * `code.textContent`, which unescapes them — so the string mermaid receives is
 * the fence content byte for byte.
 *
 * Usage:
 *     node scripts/mermaid-check/check.mjs [dir ...]     # default: docs
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { JSDOM } from "jsdom";

// mermaid is a browser library: it touches document/window at import time, so a
// DOM has to exist first.
const dom = new JSDOM("<!doctype html><html><body></body></html>");
global.window = dom.window;
global.document = dom.window.document;
// navigator is getter-only on newer Node globals, so plain assignment throws.
Object.defineProperty(global, "navigator", {
  value: dom.window.navigator,
  configurable: true,
});

const mermaid = (await import("mermaid")).default;
mermaid.initialize({ startOnLoad: false });

const FENCE = /```mermaid\n([\s\S]*?)```/g;

function markdownFiles(dir) {
  let found = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) found = found.concat(markdownFiles(path));
    else if (name.endsWith(".md")) found.push(path);
  }
  return found;
}

/** Each mermaid fence in `text`, with the 1-based line its content starts on. */
function diagrams(text) {
  const found = [];
  for (const match of text.matchAll(FENCE)) {
    const line = text.slice(0, match.index).split("\n").length + 1;
    found.push({ line, code: match[1] });
  }
  return found;
}

const roots = process.argv.slice(2);
const targets = roots.length ? roots : ["docs"];

let checked = 0;
const failures = [];

for (const root of targets) {
  for (const file of markdownFiles(root)) {
    const text = readFileSync(file, "utf8");
    for (const { line, code } of diagrams(text)) {
      checked++;
      try {
        await mermaid.parse(code);
      } catch (error) {
        failures.push({
          where: `${relative(process.cwd(), file)}:${line}`,
          detail: String(error?.message ?? error),
        });
      }
    }
  }
}

if (failures.length) {
  console.error(`\n${failures.length} of ${checked} mermaid diagram(s) failed to parse:\n`);
  for (const { where, detail } of failures) {
    // First line of the mermaid error carries the offending text and a caret;
    // the token list that follows is pages long and helps nobody.
    console.error(`  ${where}`);
    for (const row of detail.split("\n").slice(0, 3)) {
      console.error(`    ${row}`);
    }
    console.error("");
  }
  console.error(
    "These render as plain text on the site. Common causes: a ';' in a " +
      "sequence-diagram message (mermaid reads it as a statement separator), " +
      "or a bare quoted string where a node id belongs.\n",
  );
  process.exit(1);
}

console.log(`All ${checked} mermaid diagram(s) parsed.`);
