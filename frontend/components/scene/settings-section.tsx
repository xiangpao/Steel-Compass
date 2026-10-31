"use client";

import { ChevronDown } from "lucide-react";

export function SettingsSection({
  title,
  subtitle,
  children,
  open = true,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  open?: boolean;
}) {
  return (
    <details className="settings-section" open={open}>
      <summary>
        <span>
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </span>
        <ChevronDown size={17} />
      </summary>
      <div className="settings-section-body">{children}</div>
    </details>
  );
}
