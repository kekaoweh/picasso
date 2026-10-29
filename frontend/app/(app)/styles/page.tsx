"use client";

import clsx from "clsx";
import { X } from "lucide-react";
import { useState } from "react";
import { useApp } from "@/components/app-context";
import { SceneSwatch } from "@/components/artwork";
import { Frame } from "@/components/frame";
import { Button, roman } from "@/components/ui";
import { api, Style, StyleInput } from "@/lib/api";

const BLANK: StyleInput = {
  name: "",
  emoji: "🎨",
  description: "",
  pacing_seconds: 3.5,
  caption_position: "bottom",
  caption_color: "#F2EFE8",
  caption_box: true,
  transition: "cut",
  brightness: 0,
  contrast: 1,
  saturation: 1,
};

export default function StylesPage() {
  const { styles, refreshStyles } = useApp();
  const [editing, setEditing] = useState<{ id: string | null; data: StyleInput } | null>(null);

  const toInput = (s: Style): StyleInput =>
    Object.fromEntries(Object.entries(s).filter(([k]) => k !== "id" && k !== "builtin")) as StyleInput;

  const remove = async (s: Style) => {
    if (!window.confirm(`Remove the “${s.name}” style? Works using it return to Explainer.`)) return;
    await api.deleteStyle(s.id);
    await refreshStyles();
  };

  const builtin = styles.filter((s) => s.builtin);
  const own = styles.filter((s) => !s.builtin);

  return (
    <div className="studio-glow h-full overflow-y-auto">
      <div className="mx-auto max-w-[1040px] px-6 pt-12 pb-28 sm:px-12 sm:pt-16">
        <div className="flex items-baseline justify-between border-b border-line-strong pb-2.5">
          <span className="label !text-muted">Styles</span>
          <span className="label">{styles.length} in the studio</span>
        </div>
        <div className="mt-10 flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-[620px]">
            <h1 className="text-[40px] leading-[1.04] font-semibold tracking-[-0.04em] sm:text-[54px]">
              A way of <span className="text-accent">seeing</span>
            </h1>
            <p className="mt-4 text-[15px] leading-relaxed text-muted">
              Each style tells the editor how to cut (pacing, tone, how words are used) and tells the
              renderer how the film should look.
            </p>
          </div>
          <Button variant="primary" onClick={() => setEditing({ id: null, data: BLANK })}>
            Compose a style
          </Button>
        </div>

        <Gallery
          title="House styles"
          styles={builtin}
          onDuplicate={(s) => setEditing({ id: null, data: { ...toInput(s), name: `${s.name}, after` } })}
        />
        {own.length > 0 && (
          <Gallery
            title="Your styles"
            styles={own}
            onDuplicate={(s) => setEditing({ id: null, data: { ...toInput(s), name: `${s.name}, after` } })}
            onEdit={(s) => setEditing({ id: s.id, data: toInput(s) })}
            onRemove={remove}
          />
        )}
      </div>

      {editing && (
        <StyleEditor
          initial={editing.data}
          isNew={!editing.id}
          onClose={() => setEditing(null)}
          onSave={async (data) => {
            if (editing.id) await api.updateStyle(editing.id, data);
            else await api.createStyle(data);
            await refreshStyles();
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function Gallery({
  title,
  styles,
  onDuplicate,
  onEdit,
  onRemove,
}: {
  title: string;
  styles: Style[];
  onDuplicate: (s: Style) => void;
  onEdit?: (s: Style) => void;
  onRemove?: (s: Style) => void;
}) {
  return (
    <section className="mt-16">
      <h2 className="mb-8 border-b border-line pb-2.5 text-[22px] leading-none font-semibold tracking-[-0.025em]">{title}</h2>
      <div className="grid grid-cols-1 gap-x-8 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
        {styles.map((s, i) => (
          <div key={s.id} className="group">
            <Frame ratio="aspect-video">
              <StylePreview style={s} />
            </Frame>
            <div className="mt-3.5 pl-0.5">
              <div className="flex items-baseline justify-between">
                <span className="label">{roman(i + 1)} · ~{s.pacing_seconds}s shots · {s.transition === "fade" ? "fades" : "hard cuts"}</span>
              </div>
              <div className="mt-1 text-[16.5px] leading-snug font-semibold tracking-[-0.015em]">{s.name}</div>
              <p className="mt-1 line-clamp-3 text-[13px] leading-relaxed text-muted">{s.description}</p>
              <div className="mt-2.5 flex gap-4 text-[12px] text-faint">
                <button className="underline-offset-4 hover:text-fg hover:underline" onClick={() => onDuplicate(s)}>Make a variation</button>
                {onEdit && <button className="underline-offset-4 hover:text-fg hover:underline" onClick={() => onEdit(s)}>Edit</button>}
                {onRemove && <button className="underline-offset-4 hover:text-brick hover:underline" onClick={() => onRemove(s)}>Remove</button>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/** The same quiet scene under each style's grade and caption treatment. */
function StylePreview({ style, large }: { style: StyleInput; large?: boolean }) {
  const filter = `brightness(${1 + style.brightness * 2}) contrast(${style.contrast}) saturate(${style.saturation})`;
  const pos = {
    top: "top-[9%]",
    center: "top-1/2 -translate-y-1/2",
    bottom: "bottom-[9%]",
    lower_third: "top-[66%]",
  }[style.caption_position];
  return (
    <div className="absolute inset-0 overflow-hidden">
      <SceneSwatch className="absolute inset-0 size-full" style={{ filter }} />
      <div className={clsx("absolute inset-x-0 flex justify-center px-4", pos)}>
        <span
          className={clsx(
            "px-2 py-0.5 text-center font-medium",
            large ? "text-[17px]" : "text-[11.5px]",
            style.caption_box ? "bg-[#1c1a17]/60" : "[text-shadow:0_1px_3px_rgba(0,0,0,.6)]",
          )}
          style={{ color: style.caption_color }}
        >
          The light changes everything
        </span>
      </div>
    </div>
  );
}

function StyleEditor({
  initial,
  isNew,
  onClose,
  onSave,
}: {
  initial: StyleInput;
  isNew: boolean;
  onClose: () => void;
  onSave: (data: StyleInput) => Promise<void>;
}) {
  const [data, setData] = useState<StyleInput>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof StyleInput>(k: K, v: StyleInput[K]) => setData((d) => ({ ...d, [k]: v }));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSave(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save");
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-fg/25 p-4 pt-[6vh]" onMouseDown={onClose}>
      <div className="fade-up w-full max-w-[680px] border border-line-strong bg-paper shadow-pop" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-baseline justify-between border-b border-line px-6 py-3.5">
          <span className="label !text-muted">{isNew ? "Compose a style" : "Edit style"}</span>
          <button onClick={onClose} className="p-1 text-faint hover:text-fg" aria-label="Close"><X className="size-4" strokeWidth={1.5} /></button>
        </div>

        <div className="space-y-7 p-6">
          <div className="border border-line p-2">
            <div className="relative aspect-video">
              <StylePreview style={data} large />
            </div>
          </div>

          <input
            value={data.name}
            onChange={(e) => set("name", e.target.value)}
            placeholder="Name the style"
            autoFocus
            className="h-12 w-full border-b border-line-strong bg-transparent text-[24px] font-semibold tracking-[-0.025em] outline-none placeholder:text-faint placeholder:font-normal focus:border-fg"
          />

          <Field label="Direction for the editor" hint="Pacing, tone, how words are used, what to avoid. The editor reads this before every cut.">
            <textarea
              value={data.description}
              onChange={(e) => set("description", e.target.value)}
              placeholder="Warm and unhurried. Linger on faces, cut on laughter, words only at the start of each chapter…"
              className="block min-h-24 w-full resize-none border border-line-strong bg-bg px-3.5 py-2.5 text-[14.5px] leading-relaxed outline-none placeholder:text-faint focus:border-fg/60"
            />
          </Field>

          <div className="grid gap-7 sm:grid-cols-2">
            <Field label={`Average shot · ${data.pacing_seconds.toFixed(1)}s`}>
              <input type="range" min={0.5} max={12} step={0.5} value={data.pacing_seconds} onChange={(e) => set("pacing_seconds", +e.target.value)} className="w-full accent-[var(--fg)]" />
            </Field>
            <Field label="Between shots">
              <Segmented value={data.transition} options={[["cut", "Hard cut"], ["fade", "Fade"]]} onChange={(v) => set("transition", v)} />
            </Field>
            <Field label="Where words sit">
              <Segmented
                value={data.caption_position}
                options={[["top", "Top"], ["center", "Centre"], ["lower_third", "Lower ⅓"], ["bottom", "Foot"]]}
                onChange={(v) => set("caption_position", v)}
              />
            </Field>
            <Field label="How words look">
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={data.caption_color}
                  onChange={(e) => set("caption_color", e.target.value.toUpperCase())}
                  className="h-8 w-9 cursor-pointer border border-line-strong bg-paper p-0.5"
                  aria-label="Caption colour"
                />
                <Segmented value={data.caption_box ? "box" : "shadow"} options={[["box", "On a band"], ["shadow", "Bare"]]} onChange={(v) => set("caption_box", v === "box")} />
              </div>
            </Field>
          </div>

          <Field label="The grade">
            <div className="grid gap-5 sm:grid-cols-3">
              <Slider label="Light" value={data.brightness} min={-0.3} max={0.3} step={0.01} onChange={(v) => set("brightness", v)} />
              <Slider label="Contrast" value={data.contrast} min={0.5} max={1.6} step={0.01} onChange={(v) => set("contrast", v)} />
              <Slider label="Colour" value={data.saturation} min={0} max={2} step={0.01} onChange={(v) => set("saturation", v)} />
            </div>
          </Field>

          {error && <p className="text-[13px] text-brick">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 border-t border-line px-6 py-3.5">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} disabled={!data.name.trim() || !data.description.trim()} onClick={submit}>
            Save style
          </Button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="label mb-2">{label}</div>
      {hint && <div className="-mt-1 mb-2 text-[12.5px] text-faint">{hint}</div>}
      {children}
    </div>
  );
}

function Segmented<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex border border-line-strong">
      {options.map(([v, label], i) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={clsx(
            "px-2.5 py-1.5 text-[12.5px] transition-colors",
            i > 0 && "border-l border-line-strong",
            v === value ? "bg-fg text-bg" : "text-muted hover:bg-hover hover:text-fg",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <div className="mb-1.5 flex justify-between text-[12.5px] text-muted">
        <span>{label}</span>
        <span className="font-mono text-[11px] text-faint">{value.toFixed(2)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} className="w-full accent-[var(--fg)]" />
    </label>
  );
}
