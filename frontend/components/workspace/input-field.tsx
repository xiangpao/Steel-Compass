"use client";

import { HelpTip } from "@/components/help-tip";
import { NumberField } from "@/components/number-field";
import type { FieldDefinition } from "@/lib/modules";

export function InputField({
  field,
  value,
  onChange,
}: {
  field: FieldDefinition;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const label = (
    <span>
      {field.label}
      {field.help && <HelpTip term={field.label} {...field.help} />}
    </span>
  );
  if (field.type === "boolean") {
    return (
      <label className="toggle-field">
        {label}
        <button
          type="button"
          className={value ? "toggle active" : "toggle"}
          onClick={() => onChange(!value)}
          aria-pressed={Boolean(value)}
        >
          <span />
        </button>
      </label>
    );
  }
  return (
    <label className="input-field">
      {label}
      <div className="input-with-unit">
        {field.type === "select" ? (
          <select value={String(value ?? "")} onChange={(event) => onChange(event.target.value)}>
            {field.options?.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : field.type === "text" ? (
          <input type="text" value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} />
        ) : (
          <NumberField
            min={field.min}
            step={field.step ?? "any"}
            value={typeof value === "number" ? value : ""}
            onChange={onChange}
          />
        )}
        {field.unit && <small>{field.unit}</small>}
      </div>
    </label>
  );
}
