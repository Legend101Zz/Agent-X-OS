/**
 * Tiny classnames helper. Accepts strings, falsy values, and conditional
 * objects: ``cx("a", cond && "b", { c: true, d: false })``.
 */
export type ClassValue =
  | string
  | number
  | null
  | undefined
  | false
  | Record<string, boolean | null | undefined>;

export function cx(...values: ClassValue[]): string {
  const out: string[] = [];
  for (const v of values) {
    if (!v && v !== 0) continue;
    if (typeof v === "string" || typeof v === "number") {
      out.push(String(v));
    } else if (typeof v === "object") {
      for (const [key, on] of Object.entries(v)) {
        if (on) out.push(key);
      }
    }
  }
  return out.join(" ");
}