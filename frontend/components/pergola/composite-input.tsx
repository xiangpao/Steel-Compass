"use client";

import { NumberField } from "@/components/number-field";

export type CompositeItem = {
  label: string;
  value: number;
  unit: string;
  onChange: (value: number) => void;
};

const round3 = (value: number) => Number(value.toFixed(3));

/** Row of labelled number inputs joined by "×", e.g. length × width × height. */
export function CompositeInput({ items }: { items: CompositeItem[] }) {
  return (
    <div className="qa-composite-input">
      {items.map((item, index) => (
        <label key={item.label}>
          <span>{item.label}</span>
          <NumberField value={item.value} format={round3} onChange={item.onChange} />
          <em>{item.unit}</em>
          {index < items.length - 1 && <b>×</b>}
        </label>
      ))}
    </div>
  );
}

/**
 * Build composite items that each patch one numeric key of an object.
 * `fields` lists [label, key, unit, fallback]; the fallback is shown when the
 * key is unset.
 */
export function patchItems<T extends object>(
  source: T,
  update: (patch: Partial<T>) => void,
  fields: Array<[string, keyof T & string, string, number?]>,
): CompositeItem[] {
  return fields.map(([label, key, unit, fallback]) => ({
    label,
    unit,
    value: (source[key] as number | null | undefined) ?? fallback ?? 0,
    onChange: (value: number) => update({ [key]: value } as Partial<T>),
  }));
}
