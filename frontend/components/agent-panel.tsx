"use client";

import clsx from "clsx";
import { ArrowRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { StatusPill } from "@/components/status";
import { Button, roman, Spinner } from "@/components/ui";
import { ACTIVE_STATUSES, api, Asset, formatDuration, media, Run, RunEvent, timeAgo } from "@/lib/api";

/** Live event stream for one run; reconnects from the last seen event. */
function useRunEvents(run: Run | null, onFinished: () => void) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const finished = useRef(onFinished);
  finished.current = onFinished;

  useEffect(() => {
    setEvents([]);
    if (!run) return;
    let last = 0;
    let es: EventSource | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;

    const open = () => {
      es = new EventSource(`${media.events(run.id)}?after=${last}`);
      const onEvent = (e: MessageEvent) => {
        const data = JSON.parse(e.data) as RunEvent;
        last = Math.max(last, data.id);
        setEvents((prev) => (prev.some((p) => p.id === data.id) ? prev : [...prev, data]));
        if (data.type === "status" && data.status && !ACTIVE_STATUSES.includes(data.status)) finished.current();
      };
      ["status", "message", "tool", "progress", "error"].forEach((t) => es!.addEventListener(t, onEvent));
      es.addEventListener("end", () => { closed = true; es?.close(); });
      es.onerror = () => {
        es?.close();
        if (!closed) retry = setTimeout(open, 1500);
      };
    };
    open();
    return () => {
      closed = true;
      clearTimeout(retry);
      es?.close();
    };
  }, [run?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return events;
}

const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });

export function AgentPanel({
  projectId,
  runs,
  assets,
  hasTimeline,
  hasBrief,
  selectedRunId,
  onSelectRun,
  onRunsChange,
  onRunFinished,
  beforeStart,
}: {
  projectId: string;
  runs: Run[];
  assets: Asset[];
  hasTimeline: boolean;
  hasBrief: boolean;
  selectedRunId: string | null;
  onSelectRun: (id: string) => void;
  onRunsChange: (runs: Run[]) => void;
  onRunFinished: () => void;
  beforeStart?: () => Promise<void>;
}) {
  const latest = runs[0] ?? null;
  const active = latest && ACTIVE_STATUSES.includes(latest.status) ? latest : null;
  const events = useRunEvents(latest, onRunFinished);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  const start = async (mode: "agent" | "render", text = "") => {
    setBusy(true);
    setError(null);
    try {
      await beforeStart?.();
      const run = await api.startRun(projectId, text, mode);
      onRunsChange([run, ...runs]);
      setInstruction("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start");
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (active) await api.cancelRun(active.id);
  };

  const assetName = (id: unknown) => assets.find((a) => a.id === id)?.name ?? "a clip";
  const progress = [...events].reverse().find((e) => e.type === "progress");
  const status = [...events].reverse().find((e) => e.type === "status")?.status ?? latest?.status;

  const entry = (e: RunEvent): React.ReactNode => {
    if (e.type === "tool") {
      if (e.name === "list_assets") return "Surveyed the materials";
      if (e.name === "view_asset") {
        const at = typeof e.input?.start === "number" ? ` from ${formatDuration(e.input.start as number)}` : "";
        return <>Studied <em className="font-display text-[15px]">{assetName(e.input?.asset_id)}</em>{at}</>;
      }
      if (e.name === "write_script") return "Drafted the script";
      if (e.name === "set_timeline") return <>Cut the timeline{e.input?.clips ? <span className="text-faint"> · {String(e.input.clips)} shots</span> : null}</>;
      return e.label;
    }
    if (e.type === "status") {
      if (e.status === "planning") return "The editor sets to work";
      if (e.status === "rendering") return "Rendering the final cut";
      if (e.status === "done") return <span className="text-green">Finished. The piece is ready to view.</span>;
      if (e.status === "cancelled") return "Set aside";
    }
    return null;
  };

  return (
    <div className="flex h-full flex-col bg-paper">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-line px-5">
        <span className="label !text-muted">Studio log</span>
        {status && <StatusPill status={status} />}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        {!latest ? (
          <Prelude hasBrief={hasBrief} />
        ) : (
          <div>
            {latest.instruction && (
              <div className="mb-5 border-l-2 border-fg/70 pl-3.5">
                <div className="label mb-1">Your direction</div>
                <p className="text-[14px] leading-relaxed">{latest.instruction}</p>
              </div>
            )}
            <ol className="space-y-3.5">
              {events.map((e) => {
                if (e.type === "message")
                  return (
                    <li key={e.id} className="fade-up border-y border-line py-4">
                      <div className="label mb-2">Editor&apos;s note · {clock(e.at)}</div>
                      <div className="prose-doc text-[14px] leading-relaxed text-fg">
                        <ReactMarkdown>{e.text ?? ""}</ReactMarkdown>
                      </div>
                    </li>
                  );
                if (e.type === "status" && e.status === "error")
                  return (
                    <li key={e.id} className="fade-up border-l-2 border-red bg-red-soft px-3.5 py-2.5 text-[13px] leading-relaxed text-red">
                      {e.error || latest.error || "Something went wrong."}
                    </li>
                  );
                const body = entry(e);
                if (!body) return null;
                return (
                  <li key={e.id} className="fade-up grid grid-cols-[42px_1fr] items-baseline text-[13.5px] text-muted">
                    <span className="font-mono text-[10.5px] text-faint">{clock(e.at)}</span>
                    <span className="min-w-0">{body}</span>
                  </li>
                );
              })}
            </ol>
            {active && (
              <div className="mt-5 grid grid-cols-[42px_1fr] items-center">
                <Spinner className="text-accent" />
                {status === "rendering" && progress?.total ? (
                  <div>
                    <div className="mb-1.5 flex justify-between font-mono text-[10.5px] tracking-wider text-faint">
                      <span>DEVELOPING SHOTS</span>
                      <span>{progress.done} / {progress.total}</span>
                    </div>
                    <div className="h-px bg-line-strong">
                      <div className="h-px bg-accent transition-all duration-500" style={{ width: `${((progress.done ?? 0) / progress.total) * 100}%` }} />
                    </div>
                  </div>
                ) : (
                  <span className="font-display text-[15px] text-muted italic">
                    {status === "queued" ? "Preparing the studio…" : status === "rendering" ? "Rendering…" : "At work…"}
                  </span>
                )}
              </div>
            )}
            <div ref={logEnd} />
          </div>
        )}

        {runs.length > 1 && (
          <div className="mt-10">
            <div className="label mb-2 border-b border-line pb-2">Earlier states</div>
            <ol>
              {runs.map((r, i) => {
                const n = runs.length - i;
                return (
                  <li key={r.id}>
                    <button
                      disabled={!r.has_video}
                      onClick={() => onSelectRun(r.id)}
                      className={clsx(
                        "grid w-full grid-cols-[34px_1fr_auto] items-baseline gap-2 border-b border-line py-2 text-left transition-colors",
                        r.id === selectedRunId ? "text-fg" : "text-muted hover:text-fg",
                        !r.has_video && "cursor-default",
                      )}
                    >
                      <span className={clsx("font-display text-[15px]", r.id === selectedRunId ? "text-accent" : "text-faint")}>{roman(n)}.</span>
                      <span className="truncate text-[13px]">{r.instruction || (r.mode === "render" ? "Re-rendered" : "First cut")}</span>
                      {r.has_video ? <span className="font-mono text-[10px] text-faint">{timeAgo(r.created_at)}</span> : <StatusPill status={r.status} />}
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-line p-4">
        {error && <p className="mb-3 text-[13px] text-red">{error}</p>}
        {active ? (
          <Button className="w-full" onClick={stop}>
            Stop the editor
          </Button>
        ) : !hasTimeline ? (
          <div className="space-y-3">
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              rows={1}
              placeholder="Any direction for the editor? (optional)"
              className="block max-h-32 min-h-9 w-full resize-none border-b border-line-strong bg-transparent py-2 text-[14px] outline-none placeholder:text-faint focus:border-fg"
            />
            <Button
              variant="primary"
              size="lg"
              className="w-full"
              loading={busy}
              disabled={!hasBrief && !instruction.trim()}
              onClick={() => start("agent", instruction)}
            >
              Make the video
              <ArrowRight className="size-4" strokeWidth={1.5} />
            </Button>
          </div>
        ) : (
          <div>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && instruction.trim()) {
                  e.preventDefault();
                  start("agent", instruction);
                }
              }}
              rows={2}
              placeholder="Direct the next revision… “let the opening breathe, end on the wide shot”"
              className="block max-h-40 min-h-14 w-full resize-none border border-line-strong bg-bg px-3 py-2.5 text-[14px] leading-relaxed outline-none placeholder:text-faint focus:border-fg/60"
            />
            <div className="mt-2.5 flex items-center justify-between">
              <Button size="sm" variant="ghost" onClick={() => start("render")} disabled={busy} title="Render the current cut again, e.g. after changing the style or format">
                Re-render
              </Button>
              <Button size="sm" variant="primary" onClick={() => start("agent", instruction)} disabled={busy || !instruction.trim()} aria-label="Send revision">
                Revise
                <ArrowRight className="size-3.5" strokeWidth={1.5} />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Prelude({ hasBrief }: { hasBrief: boolean }) {
  const steps = [
    ["Studies the materials", "Every clip and still, frame by frame"],
    ["Drafts the script", "An opening, the movements, the words on screen"],
    ["Cuts the timeline", "Shots, captions, motion and score"],
    ["Renders the piece", "A finished film, ready to hang"],
  ];
  return (
    <div>
      <p className="font-display text-[19px] leading-snug text-muted italic">
        {hasBrief ? "When you're ready, the editor will make the whole piece." : "Write a brief, bring your materials, and the editor will make the whole piece."}
      </p>
      <ol className="mt-6 border-t border-line">
        {steps.map(([title, sub], i) => (
          <li key={title} className="grid grid-cols-[34px_1fr] border-b border-line py-3">
            <span className="font-display text-[15px] text-faint">{roman(i + 1)}.</span>
            <span>
              <span className="block text-[13.5px] font-medium">{title}</span>
              <span className="block text-[12.5px] text-faint">{sub}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
