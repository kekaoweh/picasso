"use client";

import clsx from "clsx";
import { useState } from "react";
import { Asset, Clip, formatDuration, media, Timeline } from "@/lib/api";

const GAP = 3;
const MIN_W = 30;

export function TimelineStrip({ timeline, assets }: { timeline: Timeline; assets: Asset[] }) {
  const [active, setActive] = useState<number | null>(null);
  const byId = new Map(assets.map((a) => [a.id, a]));
  const total = timeline.clips.reduce((s, c) => s + c.duration, 0);
  // Fit short edits to the width; give long ones enough room to read.
  const pxPerSec = Math.max(6, Math.min(48, 740 / Math.max(total, 1)));
  const widthOf = (c: Clip) => Math.max(MIN_W, c.duration * pxPerSec);
  const music = timeline.music ? byId.get(timeline.music.asset_id) : null;
  const starts = timeline.clips.reduce<number[]>((acc, c, i) => [...acc, i ? acc[i - 1] + timeline.clips[i - 1].duration : 0], []);
  const stripWidth = timeline.clips.reduce((s, c) => s + widthOf(c) + GAP, -GAP);

  const clip = active !== null ? timeline.clips[active] : null;
  const clipAsset = clip?.asset_id ? byId.get(clip.asset_id) : undefined;

  return (
    <div>
      <div className="overflow-x-auto pb-1">
        <div className="inline-flex min-w-full flex-col gap-2">
          <div className="film-strip px-2 py-[16px]" style={{ width: stripWidth + 16 }}>
            <div className="flex" style={{ gap: GAP }} onMouseLeave={() => setActive(null)}>
              {timeline.clips.map((c, i) => {
                const asset = c.asset_id ? byId.get(c.asset_id) : undefined;
                return (
                  <button
                    key={i}
                    type="button"
                    onMouseEnter={() => setActive(i)}
                    onFocus={() => setActive(i)}
                    onClick={() => setActive(i)}
                    className={clsx(
                      "relative h-[60px] shrink-0 overflow-hidden outline-offset-1 transition-[outline-color]",
                      active === i ? "outline-1 outline-[#e8e3d7]" : "outline-1 outline-transparent",
                    )}
                    style={{ width: widthOf(c), background: c.kind === "title_card" ? c.background : "#2a2724" }}
                    aria-label={`Shot ${i + 1}`}
                  >
                    {asset?.has_thumb && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={media.thumb(asset.id)}
                        alt=""
                        className={clsx("absolute inset-0 size-full object-cover transition-[filter] duration-300", active === i ? "" : "grayscale-[0.8] sepia-[0.1]")}
                        loading="lazy"
                      />
                    )}
                    {c.text?.text && (
                      <span
                        className={clsx(
                          "absolute inset-x-0 line-clamp-2 px-1 text-center text-[8.5px] leading-tight font-medium text-white [text-shadow:0_1px_2px_rgba(0,0,0,.85)]",
                          c.kind === "title_card" ? "top-1/2 -translate-y-1/2 text-[10px] font-semibold" : "bottom-1",
                        )}
                      >
                        {c.text.text}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
          {music && (
            <div className="flex h-7 items-center gap-3 border border-line px-3" style={{ width: stripWidth + 16 }}>
              <span className="label !text-accent">Score</span>
              <span className="min-w-0 truncate text-[12.5px] text-muted">{music.name}</span>
              <span className="ml-auto shrink-0 font-mono text-[10.5px] text-faint">{Math.round((timeline.music?.volume ?? 0) * 100)}%</span>
            </div>
          )}
        </div>
      </div>

      {/* Shot notes */}
      <div className="mt-3 min-h-[64px] border-l border-line-strong py-1 pl-4">
        {clip && active !== null ? (
          <div className="fade-up">
            <div className="label">
              Shot {active + 1} · {formatDuration(starts[active])}–{formatDuration(starts[active] + clip.duration)} ·{" "}
              {clip.kind === "title_card" ? "Title card" : clipAsset?.name ?? "Missing material"}
              {clip.kind === "asset" && clipAsset?.kind === "video" ? ` from ${clip.source_start.toFixed(1)}s` : ""}
              {clip.motion !== "none" ? ` · ${clip.motion.replace("_", " ")}` : ""}
            </div>
            {clip.text?.text && <div className="mt-1 text-[15px] font-medium leading-snug">“{clip.text.text}”</div>}
            {clip.note && <div className="mt-0.5 text-[13px] leading-relaxed text-muted">{clip.note}</div>}
          </div>
        ) : (
          <p className="text-[13.5px] text-faint">
            {timeline.clips.length} shots, {formatDuration(total)}. Hover a frame to read the editor&apos;s note on it.
          </p>
        )}
      </div>
    </div>
  );
}
