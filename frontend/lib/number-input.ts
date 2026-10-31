// Parse a number-input string; "" or a non-number yields "" so callers can
// keep an emptied field empty instead of silently using 0.
export function parseNumberInput(raw: string): number | "" {
  if (raw.trim() === "") return "";
  const value = Number(raw);
  return Number.isFinite(value) ? value : "";
}
