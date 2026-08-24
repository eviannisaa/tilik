/**
 * No em dashes in anything a reader sees.
 *
 * They set a clause apart with a mark instead of a sentence, and across a report
 * they piled up: the InaRISK reading alone carried one per hazard layer, nine to
 * a page. Rewriting each as its own sentence reads the same and looks
 * deliberate.
 *
 * Two things are exempt, and both are exempt because they are not punctuation.
 * A lone dash is the "no data" marker in a table cell, where the alternative is
 * an empty cell that reads as a rendering fault. A dash between digits is a
 * numeric range ("0.00-1.00"), where the en dash is the correct typographic
 * form. Comments are exempt too: they are for whoever reads the code.
 *
 * Sources are read through `import.meta.glob` rather than `node:fs`, which the
 * project has no type definitions for.
 */

import { describe, expect, it } from "vitest";

const EM_DASH = "—";
const EN_DASH = "–";

const SOURCES = import.meta.glob("../**/*.{ts,tsx,astro}", {
     query: "?raw",
     import: "default",
     eager: true,
}) as Record<string, string>;

/** Everything the reader could see, with the exempt cases removed. */
function readerText(source: string): string {
     return source
          .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
          .replace(/\/\*[\s\S]*?\*\//g, "")
          .replace(/^\s*\/\/.*$/gm, "")
          .replace(/(\?\?|:|return)\s*["']—["']/g, "")
          .replace(/^\s*—\s*$/gm, "")
          .replace(/\d\s*[—–]\s*\d/g, "");
}

function offenders(dash: string): string[] {
     const found: string[] = [];
     for (const [path, source] of Object.entries(SOURCES)) {
          // Glob paths are relative to this file, so its own directory has no
          // marker in them: match the filename instead.
          if (/\.test\.[tj]sx?$/.test(path)) continue;
          readerText(source)
               .split("\n")
               .forEach((line, index) => {
                    if (line.includes(dash)) {
                         found.push(`${path}:${index + 1} ${line.trim().slice(0, 60)}`);
                    }
               });
     }
     return found;
}

describe("report copy", () => {
     it.each([
          { name: "em dash", dash: EM_DASH },
          { name: "en dash", dash: EN_DASH },
     ])("uses no $name", ({ dash }) => {
          expect(offenders(dash)).toEqual([]);
     });

     it("scans something, so a pass means something", () => {
          // A guard that silently matches nothing guards nothing.
          expect(Object.keys(SOURCES).length).toBeGreaterThan(20);
     });
});
