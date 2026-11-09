import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// An effect with an expression body returns that expression's value. Browser APIs such as
// scrollIntoView now return Promises, which React then tries to call as a cleanup function
// ("useEffect must not return anything besides a function" / "u is not a function").
const ROOTS = ["app", "components", "hooks", "lib"];
const EXPRESSION_BODY = /useEffect\(\s*(async\s*)?\(\s*\)\s*=>(?!\s*\{)/;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(tsx?|jsx?)$/.test(name) ? [path] : [];
  });
}

describe("effects", () => {
  it("always use a block body (never return a value from useEffect)", () => {
    const offenders = ROOTS.flatMap((root) => sourceFiles(root)).filter((file) =>
      EXPRESSION_BODY.test(readFileSync(file, "utf-8")),
    );
    expect(offenders).toEqual([]);
  });
});
