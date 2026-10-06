// Matches the selector path segment "f" (a bound flow) | "u" (an unbound selector)
// (design §4.1: p/[project]/[kind=selkind]/[sel]/...).
export type SelKind = "f" | "u";

/** @param {string} param */
export function match(param) {
  return param === "f" || param === "u";
}