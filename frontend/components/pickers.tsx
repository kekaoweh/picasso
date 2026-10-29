"use client";

import clsx from "clsx";
import { Check } from "lucide-react";
import { ReactNode, useState } from "react";
import { Menu, MenuItem } from "@/components/ui";
import { Aspect, formatLength, Style } from "@/lib/api";

export const LENGTHS = [15, 30, 60, 90, 180, 300, 600, 900, 1200, 1800];

/** A spec-sheet field: small label over an underlined value that opens a menu. */
function Field({ label, open, toggle, children }: { label?: string; open: boolean; toggle: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={toggle} className="group flex flex-col items-start text-left">
      {label && <span className="label mb-1">{label}</span>}
      <span
        className={clsx(
          "border-b border-dotted pb-px text-[14px] transition-colors",
          open ? "border-fg text-fg" : "border-line-strong text-fg/85 group-hover:border-fg group-hover:text-fg",
        )}
      >
        {children}
      </span>
    </button>
  );
}

export function LengthPicker({ value, onChange, label }: { value: number; onChange: (v: number) => void; label?: string }) {
  const [custom, setCustom] = useState("");
  return (
    <Menu
      width="w-52"
      trigger={({ open, toggle }) => (
        <Field label={label} open={open} toggle={toggle}>{formatLength(value)}</Field>
      )}
    >
      {(close) => (
        <>
          <div className="label px-2.5 pt-1.5 pb-1">Running time</div>
          {LENGTHS.map((s) => (
            <MenuItem key={s} onClick={() => { onChange(s); close(); }} hint={s === value ? <Check className="size-3.5" strokeWidth={1.5} /> : null}>
              {formatLength(s)}
            </MenuItem>
          ))}
          <form
            className="mt-1 border-t border-line px-1 pt-1.5 pb-0.5"
            onSubmit={(e) => {
              e.preventDefault();
              const secs = parseDuration(custom);
              if (secs) { onChange(secs); close(); setCustom(""); }
            }}
          >
            <input
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              placeholder="Custom, e.g. 2:30 or 45s"
              className="h-7 w-full border-b border-line bg-transparent px-1.5 text-[13px] outline-none placeholder:text-faint focus:border-fg"
            />
          </form>
        </>
      )}
    </Menu>
  );
}

function parseDuration(text: string): number | null {
  const t = text.trim().toLowerCase();
  let secs: number | null = null;
  if (/^\d+:\d{1,2}$/.test(t)) {
    const [m, s] = t.split(":").map(Number);
    secs = m * 60 + s;
  } else if (/^\d+(\.\d+)?\s*(m|min|mins|minutes?)$/.test(t)) secs = Math.round(parseFloat(t) * 60);
  else if (/^\d+\s*(s|sec|secs|seconds?)?$/.test(t)) secs = parseInt(t, 10);
  if (!secs) return null;
  return Math.min(Math.max(secs, 5), 3600);
}

/** Proportional outline of the frame, so the format reads at a glance. */
function FrameIcon({ aspect }: { aspect: Aspect }) {
  const [w, h] = { "16:9": [16, 9], "9:16": [9, 16], "1:1": [12, 12], "4:5": [11, 13.75] }[aspect];
  return <span className="inline-block border border-current" style={{ width: w, height: h }} />;
}

const ASPECTS: { value: Aspect; label: string }[] = [
  { value: "16:9", label: "Landscape" },
  { value: "9:16", label: "Vertical" },
  { value: "1:1", label: "Square" },
  { value: "4:5", label: "Portrait" },
];

export function AspectPicker({ value, onChange, label }: { value: Aspect; onChange: (v: Aspect) => void; label?: string }) {
  const current = ASPECTS.find((a) => a.value === value) ?? ASPECTS[0];
  return (
    <Menu
      width="w-48"
      trigger={({ open, toggle }) => (
        <Field label={label} open={open} toggle={toggle}>
          {current.label} <span className="text-faint">{current.value}</span>
        </Field>
      )}
    >
      {(close) =>
        ASPECTS.map((a) => (
          <MenuItem key={a.value} icon={<FrameIcon aspect={a.value} />} active={a.value === value} hint={a.value} onClick={() => { onChange(a.value); close(); }}>
            {a.label}
          </MenuItem>
        ))
      }
    </Menu>
  );
}

export function StylePicker({
  styles,
  value,
  onChange,
  label,
}: {
  styles: Style[];
  value: string | null;
  onChange: (v: string) => void;
  label?: string;
}) {
  const current = styles.find((s) => s.id === value);
  return (
    <Menu
      width="w-80"
      trigger={({ open, toggle }) => (
        <Field label={label} open={open} toggle={toggle}>
          <span className="font-display text-[16px] italic">{current?.name ?? "Choose a style"}</span>
        </Field>
      )}
    >
      {(close) => (
        <div className="max-h-80 overflow-y-auto">
          {styles.map((s) => (
            <button
              key={s.id}
              onClick={() => { onChange(s.id); close(); }}
              className={clsx("block w-full rounded-[2px] px-2.5 py-2 text-left hover:bg-hover", s.id === value && "bg-hover")}
            >
              <span className="flex items-baseline justify-between gap-3">
                <span className="font-display text-[17px] italic">{s.name}</span>
                <span className="font-mono text-[10px] tracking-wider text-faint">~{s.pacing_seconds}s</span>
              </span>
              <span className="mt-0.5 line-clamp-2 block text-[12px] leading-snug text-muted">{s.description}</span>
            </button>
          ))}
        </div>
      )}
    </Menu>
  );
}
