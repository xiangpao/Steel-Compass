"use client";

import { useState, type InputHTMLAttributes } from "react";
import { parseNumberInput } from "@/lib/number-input";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> & {
  value: number | "" | null | undefined;
  onChange: (value: number) => void;
  /** Display transform for a committed value, e.g. rounding. */
  format?: (value: number) => number;
};

/**
 * Number input that never turns an emptied field into 0. While the text is
 * empty or not a number it is marked invalid and nothing is committed; on blur
 * the field shows the last committed value again.
 */
export function NumberField({ value, onChange, format, onBlur, ...rest }: Props) {
  const [draft, setDraft] = useState<string | null>(null);
  const committed = typeof value === "number" && Number.isFinite(value)
    ? String(format ? format(value) : value)
    : "";
  const invalid = draft !== null && parseNumberInput(draft) === "";
  return (
    <input
      {...rest}
      type="number"
      value={draft ?? committed}
      aria-invalid={invalid || undefined}
      onChange={(event) => {
        setDraft(event.target.value);
        const parsed = parseNumberInput(event.target.value);
        if (parsed !== "") onChange(parsed);
      }}
      onBlur={(event) => {
        setDraft(null);
        onBlur?.(event);
      }}
    />
  );
}
