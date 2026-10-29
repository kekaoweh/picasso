"use client";

import clsx from "clsx";
import { X } from "lucide-react";
import { DragEvent, useRef, useState } from "react";
import { Menu, MenuItem, useDebouncedCallback } from "@/components/ui";
import { api, Asset, AssetRole, formatDuration, media, uploadAssets } from "@/lib/api";

const ROLES: { value: AssetRole; label: string; hint: string }[] = [
  { value: "footage", label: "Footage", hint: "Cut into the film" },
  { value: "reference", label: "Reference", hint: "A look or pace to match" },
  { value: "music", label: "Score", hint: "The soundtrack" },
];

export function AssetGrid({
  projectId,
  assets,
  onChange,
}: {
  projectId: string;
  assets: Asset[];
  onChange: (assets: Asset[]) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = async (files: File[]) => {
    if (!files.length) return;
    setError(null);
    setProgress(0);
    try {
      const created = await uploadAssets(projectId, files, setProgress);
      onChange([...assets, ...created]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setProgress(null);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    upload(Array.from(e.dataTransfer.files));
  };

  const update = (asset: Asset) => onChange(assets.map((a) => (a.id === asset.id ? asset : a)));
  const remove = async (asset: Asset) => {
    onChange(assets.filter((a) => a.id !== asset.id));
    await api.deleteAsset(asset.id);
  };

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => progress === null && input.current?.click()}
        className={clsx(
          "flex cursor-pointer flex-col items-center justify-center border border-dashed px-4 text-center transition-colors",
          assets.length ? "py-6" : "py-12",
          dragging ? "border-fg bg-hover" : "border-line-strong hover:border-fg/40 hover:bg-hover",
        )}
      >
        <input
          ref={input}
          type="file"
          multiple
          accept="video/*,image/*,audio/*"
          className="hidden"
          onChange={(e) => { upload(Array.from(e.target.files ?? [])); e.target.value = ""; }}
        />
        {progress !== null ? (
          <div className="w-full max-w-xs">
            <div className="label mb-2.5">{progress < 1 ? `Receiving · ${Math.round(progress * 100)}%` : "Preparing the materials"}</div>
            <div className="h-px bg-line-strong">
              <div className="h-px bg-fg transition-all" style={{ width: `${progress * 100}%` }} />
            </div>
          </div>
        ) : (
          <>
            <p className="text-[15px] font-medium text-muted">
              {assets.length ? "Add your own footage, stills, references or music" : "Optional: bring your own footage, stills, references or music"}
            </p>
            <p className="mt-1 text-[12.5px] text-faint">
              or <span className="text-fg underline decoration-line-strong underline-offset-4">browse your files</span>
{!assets.length && " · or leave this empty and the editor finds everything"}
            </p>
          </>
        )}
      </div>
      {error && <p className="mt-2 text-[13px] text-brick">{error}</p>}

      {assets.length > 0 && (
        <div className="mt-6 grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-3">
          {assets.map((a, i) => (
            <AssetCard key={a.id} index={i + 1} asset={a} onUpdate={update} onRemove={() => remove(a)} />
          ))}
        </div>
      )}
    </div>
  );
}

function AssetCard({ asset, index, onUpdate, onRemove }: { asset: Asset; index: number; onUpdate: (a: Asset) => void; onRemove: () => void }) {
  const [note, setNote] = useState(asset.note);
  const saveNote = useDebouncedCallback(async (value: string) => {
    onUpdate(await api.updateAsset(asset.id, { note: value }));
  }, 600);
  const role = ROLES.find((r) => r.value === asset.role) ?? ROLES[0];
  const meta = asset.kind === "image" ? `Still · ${asset.width}×${asset.height}` : `${asset.kind === "video" ? "Film" : "Sound"} · ${formatDuration(asset.duration)}`;

  return (
    <div className="group">
      <div className="border border-line bg-paper p-1.5">
        <div className="relative aspect-[4/3] overflow-hidden bg-soft">
          {asset.has_thumb ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={media.thumb(asset.id)} alt="" className="gallery-img size-full object-cover" loading="lazy" />
          ) : (
            <div className="flex size-full items-center justify-center text-faint">
              <Waveform />
            </div>
          )}
          <button
            onClick={onRemove}
            className="absolute top-1.5 right-1.5 bg-paper/90 p-1 text-muted opacity-0 transition-opacity group-hover:opacity-100 hover:text-brick"
            aria-label={`Remove ${asset.name}`}
          >
            <X className="size-3.5" strokeWidth={1.5} />
          </button>
        </div>
      </div>
      <div className="mt-2.5 px-0.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="label">{String(index).padStart(2, "0")} · {meta}</span>
          <Menu
            align="right"
            width="w-60"
            trigger={({ toggle }) => (
              <button
                onClick={toggle}
                aria-label={role.label}
                className={clsx(
                  "shrink-0 border-b border-dotted font-mono text-[10px] font-medium tracking-[0.12em] uppercase transition-colors",
                  asset.role === "reference" ? "border-accent text-accent" : asset.role === "music" ? "border-dusk text-dusk" : "border-line-strong text-muted hover:text-fg",
                )}
              >
                {role.label}
              </button>
            )}
          >
            {(close) =>
              ROLES.map((r) => (
                <MenuItem
                  key={r.value}
                  hint={r.hint}
                  active={r.value === asset.role}
                  onClick={async () => { close(); onUpdate(await api.updateAsset(asset.id, { role: r.value })); }}
                >
                  {r.label}
                </MenuItem>
              ))
            }
          </Menu>
        </div>
        <div className="mt-1 truncate text-[13px]" title={asset.name}>{asset.name}</div>
        {asset.source !== "upload" && (
          <a
            href={asset.source_url || undefined}
            target="_blank"
            rel="noreferrer"
            title={[asset.credit && `By ${asset.credit}`, asset.license].filter(Boolean).join(" · ")}
            className="mt-0.5 block truncate text-[11.5px] text-faint underline-offset-2 hover:text-muted hover:underline"
          >
            Found on {asset.source} · {asset.license}
          </a>
        )}
        <input
          value={note}
          onChange={(e) => { setNote(e.target.value); saveNote(e.target.value); }}
          placeholder="A note for the editor…"
          className="mt-1 h-6 w-full border-b border-transparent bg-transparent text-[13px] text-muted outline-none placeholder:text-faint hover:border-line focus:border-line-strong"
        />
      </div>
    </div>
  );
}

function Waveform() {
  const bars = [6, 14, 9, 20, 12, 24, 10, 17, 8, 15, 22, 11, 7, 18, 10, 13, 6];
  return (
    <div className="flex h-8 items-center gap-[3px]">
      {bars.map((h, i) => (
        <span key={i} className="w-px bg-current" style={{ height: h }} />
      ))}
    </div>
  );
}
