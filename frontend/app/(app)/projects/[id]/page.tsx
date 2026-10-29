"use client";

import clsx from "clsx";
import { Download, MoreHorizontal, PanelRightClose, PanelRightOpen, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { AgentPanel } from "@/components/agent-panel";
import { useApp } from "@/components/app-context";
import { AssetGrid } from "@/components/asset-grid";
import { AspectPicker, LengthPicker, StylePicker } from "@/components/pickers";
import { StatusPill } from "@/components/status";
import { TimelineStrip } from "@/components/timeline-strip";
import { Button, Menu, MenuItem, plate, roman, SectionTitle, Spinner, useMediaQuery } from "@/components/ui";
import { api, Aspect, formatDuration, media, Project, Run, timeAgo } from "@/lib/api";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { styles, patchProjectSummary, refreshProjects, plateOf } = useApp();
  const [project, setProject] = useState<Project | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const [tab, setTab] = useState<"timeline" | "script">("timeline");
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  const load = useCallback(async () => {
    try {
      const [p, r] = await Promise.all([api.project(id), api.runs(id)]);
      setProject(p);
      setRuns(r);
      setSelectedRunId(r.find((x) => x.has_video)?.id ?? null);
    } catch {
      setNotFound(true);
    }
  }, [id]);

  useEffect(() => {
    setProject(null);
    load();
  }, [load]);

  // Edits are merged into one pending patch so a quick title-then-brief edit saves both.
  const pending = useRef<Partial<Project>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flush = useCallback(async (keepalive = false) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    const patch = pending.current;
    pending.current = {};
    if (Object.keys(patch).length) await api.updateProject(id, patch, keepalive);
  }, [id]);

  useEffect(() => {
    const onUnload = () => { flush(true); };
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      flush(true);
    };
  }, [flush]);

  const change = (patch: Partial<Project>, immediate = false) => {
    setProject((p) => (p ? { ...p, ...patch } : p));
    if ("name" in patch || "emoji" in patch) patchProjectSummary(id, patch);
    pending.current = { ...pending.current, ...patch };
    if (immediate) flush();
    else {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => flush(), 500);
    }
  };

  const onRunFinished = useCallback(async () => {
    await load();
    refreshProjects();
  }, [load, refreshProjects]);

  const onRunsChange = (next: Run[]) => {
    setRuns(next);
    patchProjectSummary(id, { latest_status: next[0]?.status ?? null });
  };

  const remove = async () => {
    if (!project || !window.confirm(`Remove “${project.name || "Untitled"}” and all its materials?`)) return;
    await api.deleteProject(id);
    await refreshProjects();
    router.push("/");
  };

  if (notFound)
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted">
        <span className="text-[18px] font-medium">This work isn&apos;t in the collection.</span>
        <Link href="/" className="text-fg underline underline-offset-4">Back to the studio</Link>
      </div>
    );
  if (!project)
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );

  const selectedRun = runs.find((r) => r.id === selectedRunId && r.has_video);
  const selectedIndex = selectedRun ? runs.length - runs.indexOf(selectedRun) : 0;
  const portrait = project.aspect === "9:16" || project.aspect === "4:5";
  const begun = new Date(project.created_at).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
  const panel = (
    <AgentPanel
      projectId={project.id}
      runs={runs}
      assets={project.assets}
      hasTimeline={!!project.timeline}
      hasBrief={!!project.prompt.trim()}
      selectedRunId={selectedRunId}
      onSelectRun={setSelectedRunId}
      onRunsChange={onRunsChange}
      onRunFinished={onRunFinished}
      beforeStart={flush}
    />
  );

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <div className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-5">
          <div className="flex min-w-0 items-baseline gap-2 text-[13px]">
            <Link href="/" className="text-muted hover:text-fg">Studio</Link>
            <span className="text-faint">/</span>
            <span className="label !text-fg">{plate(plateOf(project.id))}</span>
          </div>
          <div className="ml-auto flex items-center gap-1">
            {runs[0] && <span className="mr-2"><StatusPill status={runs[0].status} /></span>}
            {selectedRun && (
              <a href={media.video(selectedRun.id, true)}>
                <Button size="sm" variant="ghost" icon={<Download className="size-3.5" strokeWidth={1.5} />}>Download</Button>
              </a>
            )}
            <Menu
              align="right"
              width="w-48"
              trigger={({ toggle }) => (
                <Button size="sm" variant="ghost" onClick={toggle} aria-label="More">
                  <MoreHorizontal className="size-4" strokeWidth={1.5} />
                </Button>
              )}
            >
              {() => (
                <MenuItem icon={<Trash2 className="size-3.5" strokeWidth={1.5} />} danger onClick={remove}>
                  Remove this work
                </MenuItem>
              )}
            </Menu>
            {isDesktop && (
              <Button size="sm" variant="ghost" onClick={() => setPanelOpen((o) => !o)} aria-label="Toggle studio log">
                {panelOpen ? <PanelRightClose className="size-4" strokeWidth={1.5} /> : <PanelRightOpen className="size-4" strokeWidth={1.5} />}
              </Button>
            )}
          </div>
        </div>

        {/* The entry */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[780px] px-6 pt-12 pb-32 sm:px-12">
            <div className="label">{plate(plateOf(project.id))} · Begun {begun}</div>
            <textarea
              value={project.name}
              onChange={(e) => change({ name: e.target.value.replace(/\n/g, "") })}
              onKeyDown={(e) => e.key === "Enter" && e.preventDefault()}
              rows={1}
              placeholder="Untitled"
              aria-label="Title"
              className="mt-3 block w-full resize-none bg-transparent text-[34px] leading-[1.08] font-semibold tracking-[-0.035em] outline-none placeholder:text-faint sm:text-[44px]"
            />

            {/* Spec band */}
            <div className="mt-7 grid grid-cols-2 gap-y-5 border-y border-line py-4 sm:grid-cols-3">
              <LengthPicker label="Running time" value={project.target_seconds} onChange={(v) => change({ target_seconds: v }, true)} />
              <AspectPicker label="Format" value={project.aspect} onChange={(v: Aspect) => change({ aspect: v }, true)} />
              <div className="flex items-end gap-3">
                <StylePicker label="Style" styles={styles} value={project.style_id} onChange={(v) => change({ style_id: v }, true)} />
                <Link href="/styles" className="pb-0.5 text-[11.5px] text-faint hover:text-muted">edit styles</Link>
              </div>
            </div>

            <section className="mt-12">
              <SectionTitle n={1}>The brief</SectionTitle>
              <textarea
                value={project.prompt}
                onChange={(e) => change({ prompt: e.target.value })}
                placeholder="What is the piece about? Who is it for? How should it feel? Name the moments it must have, the chapters, how it ends…"
                className="block min-h-28 w-full resize-none bg-transparent text-[16.5px] leading-[1.7] outline-none placeholder:text-faint"
              />
            </section>

            {selectedRun && (
              <section className="mt-12">
                <SectionTitle n={2}>The piece</SectionTitle>
                <figure className={clsx(portrait && "mx-auto max-w-[380px]")}>
                  <div className="border border-line bg-paper p-3 shadow-card">
                    <video
                      key={selectedRun.id}
                      src={`${media.video(selectedRun.id)}#t=0.6`}
                      preload="metadata"
                      controls
                      playsInline
                      className="block max-h-[70vh] w-full bg-film"
                    />
                  </div>
                  <figcaption className="mt-3 flex items-baseline justify-between gap-4">
                    <span className="text-[14.5px] font-medium">{project.name || "Untitled"}, state {roman(selectedIndex)}.</span>
                    <span className="label">{formatDuration(selectedRun.duration)} · {project.aspect} · {timeAgo(selectedRun.created_at)}</span>
                  </figcaption>
                </figure>
              </section>
            )}

            {(project.timeline || project.script) && (
              <section className="mt-12">
                <SectionTitle
                  n={selectedRun ? 3 : 2}
                  action={
                    <div className="flex gap-4">
                      {(["timeline", "script"] as const).map((t) => (
                        <button
                          key={t}
                          onClick={() => setTab(t)}
                          className={clsx(
                            "font-mono text-[10.5px] tracking-[0.14em] uppercase transition-colors",
                            tab === t ? "text-fg underline decoration-accent decoration-1 underline-offset-[6px]" : "text-faint hover:text-muted",
                          )}
                        >
                          {t === "timeline" ? "Cut" : "Script"}
                        </button>
                      ))}
                    </div>
                  }
                >
                  The cut
                </SectionTitle>
                {tab === "timeline" ? (
                  project.timeline ? (
                    <TimelineStrip timeline={project.timeline} assets={project.assets} />
                  ) : (
                    <p className="text-[14px] text-faint">No cut yet.</p>
                  )
                ) : project.script ? (
                  <div className="prose-doc text-[15.5px]">
                    <ReactMarkdown>{project.script}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="text-[14px] text-faint">No script yet.</p>
                )}
              </section>
            )}

            <section className="mt-12">
              <SectionTitle n={(selectedRun ? 3 : 2) + (project.timeline || project.script ? 1 : 0)}>Materials</SectionTitle>
              <p className="-mt-1 mb-5 text-[13.5px] leading-relaxed text-muted">
                Tag a piece as <span className="font-mono text-[10.5px] tracking-[0.12em] text-accent">REFERENCE</span> to show the editor a look or pace to match,
                and sound as <span className="font-mono text-[10.5px] tracking-[0.12em] text-blue">SCORE</span> for the soundtrack.
              </p>
              <AssetGrid projectId={project.id} assets={project.assets} onChange={(assets) => setProject({ ...project, assets })} />
            </section>
          </div>
        </div>

        {/* Studio log below the entry on small screens */}
        {!isDesktop && <div className="h-[45vh] shrink-0 border-t border-line">{panel}</div>}
      </div>

      {isDesktop && panelOpen && <div className="w-[384px] shrink-0 border-l border-line">{panel}</div>}
    </div>
  );
}
