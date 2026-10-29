"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useApp } from "@/components/app-context";
import { BlankCanvas, Frame } from "@/components/frame";
import { AspectPicker, LengthPicker, StylePicker } from "@/components/pickers";
import { StatusPill } from "@/components/status";
import { Button, plate, roman } from "@/components/ui";
import { Aspect, api, formatLength, media, timeAgo } from "@/lib/api";

const SKETCHES = [
  "A sixty-second recap of our team offsite, warm and funny, names on screen",
  "A ten-minute essay on why film cameras are coming back",
  "A thirty-second vertical teaser for a product launch, with a hook in the first breath",
  "A quiet travel diary from Japan, in chapters by city",
];

export default function StudioPage() {
  const { user, projects, styles, refreshProjects, plateOf } = useApp();
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [seconds, setSeconds] = useState(60);
  const [aspect, setAspect] = useState<Aspect>("16:9");
  const [styleId, setStyleId] = useState("sty_explainer");
  const [busy, setBusy] = useState(false);

  const begin = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const firstLine = prompt.trim().split(/[.\n]/)[0];
      const name = firstLine ? firstLine.slice(0, 60) : "Untitled";
      const p = await api.createProject({ name, prompt: prompt.trim(), target_seconds: seconds, aspect, style_id: styleId });
      await refreshProjects();
      router.push(`/projects/${p.id}`);
    } catch {
      setBusy(false);
    }
  };

  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1040px] px-6 pt-12 pb-28 sm:px-12 sm:pt-16">
        {/* Masthead */}
        <div className="flex items-baseline justify-between border-b border-fg/80 pb-2.5">
          <span className="label !text-muted">The studio of {user.name}</span>
          <span className="label hidden sm:inline">{today}</span>
        </div>

        <h1 className="mt-10 max-w-[760px] text-[40px] leading-[1.04] font-semibold tracking-[-0.04em] sm:text-[58px]">
          What shall we <span className="text-accent">make</span> today?
        </h1>

        <div className="mt-10 grid gap-10 lg:grid-cols-[1fr_280px]">
          {/* Commission sheet */}
          <div className="self-start border border-line-strong bg-paper shadow-card transition-shadow focus-within:shadow-pop">
            <div className="flex items-baseline justify-between border-b border-line px-5 py-2.5">
              <span className="label">New commission</span>
              <span className="label">{plate(projects.length + 1)}</span>
            </div>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) begin();
              }}
              rows={4}
              placeholder="Describe the piece: its subject, who it's for, how it should feel. Footage, stills and music come next."
              className="block max-h-80 min-h-32 w-full resize-none bg-transparent px-5 pt-4 pb-2 text-[16px] leading-relaxed outline-none placeholder:text-faint"
            />
            <div className="flex flex-wrap items-end gap-x-8 gap-y-4 border-t border-line px-5 py-4">
              <LengthPicker label="Running time" value={seconds} onChange={setSeconds} />
              <AspectPicker label="Format" value={aspect} onChange={setAspect} />
              <StylePicker label="Style" styles={styles} value={styleId} onChange={setStyleId} />
              <Button variant="primary" className="ml-auto" onClick={begin} loading={busy} title="Begin (⌘↵)" aria-label="Begin the work">
                Begin
                <ArrowRight className="size-4" strokeWidth={1.5} />
              </Button>
            </div>
          </div>

          {/* Sketchbook */}
          <aside>
            <div className="label mb-3 border-b border-line pb-2">From the sketchbook</div>
            <ol className="space-y-3">
              {SKETCHES.map((s, i) => (
                <li key={s} className="grid grid-cols-[34px_1fr]">
                  <span className="font-mono text-[11px] leading-[22px] text-faint">{roman(i + 1)}.</span>
                  <button
                    onClick={() => setPrompt(s)}
                    className="text-left text-[14.5px] leading-[22px] text-muted decoration-line-strong underline-offset-4 transition-colors hover:text-fg hover:underline"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ol>
          </aside>
        </div>

        {/* The collection */}
        <section className="mt-24">
          <div className="mb-8 flex items-baseline justify-between border-b border-line pb-2.5">
            <h2 className="text-[24px] leading-none font-semibold tracking-[-0.025em]">The collection</h2>
            <span className="label">{projects.length} {projects.length === 1 ? "work" : "works"}</span>
          </div>
          {projects.length === 0 ? (
            <div className="grid place-items-center py-16 text-center">
              <p className="text-[18px] font-medium tracking-[-0.01em] text-muted">The walls are bare.</p>
              <p className="mt-1 text-[13px] text-faint">Begin a commission above and it will hang here.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-x-8 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
              {projects.map((p) => (
                <Link key={p.id} href={`/projects/${p.id}`} className="group block">
                  <Frame>
                    {p.cover_asset_id ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={media.thumb(p.cover_asset_id)} alt="" className="gallery-img size-full object-cover group-hover:scale-[1.02]" />
                    ) : (
                      <BlankCanvas label="Awaiting materials" />
                    )}
                    {p.latest_status && p.latest_status !== "done" && (
                      <div className="absolute top-2 left-2">
                        <StatusPill status={p.latest_status} solid />
                      </div>
                    )}
                  </Frame>
                  {/* Placard */}
                  <div className="mt-3.5 pl-0.5">
                    <div className="label">{plate(plateOf(p.id))}</div>
                    <div className="mt-1 text-[16.5px] leading-snug font-semibold tracking-[-0.015em] decoration-line-strong underline-offset-4 group-hover:underline">
                      {p.name || "Untitled"}
                    </div>
                    <div className="mt-1 text-[12.5px] text-faint">
                      Moving picture, {formatLength(p.target_seconds)} · {p.aspect} · {timeAgo(p.updated_at)}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
