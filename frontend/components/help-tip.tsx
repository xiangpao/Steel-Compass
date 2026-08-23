"use client";

import { CircleHelp } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

type Props = {
  term: string;
  what: string;
  adopted: string;
  changeWhen: string;
};

export function HelpTip({ term, what, adopted, changeWhen }: Props) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    function close(event: KeyboardEvent | MouseEvent | TouchEvent) {
      if (event instanceof KeyboardEvent) {
        if (event.key === "Escape") setOpen(false);
        return;
      }
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", close);
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    return () => {
      document.removeEventListener("keydown", close);
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
    };
  }, []);

  return (
    <span
      className="help-tip"
      ref={root}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={`查看${term}说明`}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
        onFocus={() => setOpen(true)}
      >
        <CircleHelp size={15} aria-hidden="true" />
      </button>
      {open && (
        <span className="help-tip-panel" id={id} role="tooltip">
          <strong>{term}</strong>
          <span><b>是什么：</b>{what}</span>
          <span><b>软件怎样采用：</b>{adopted}</span>
          <span><b>什么时候需要修改：</b>{changeWhen}</span>
        </span>
      )}
    </span>
  );
}
