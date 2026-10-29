import clsx from "clsx";
import { RunStatus } from "@/lib/api";

export const STATUS_LABELS: Record<RunStatus, string> = {
  queued: "Preparing",
  planning: "In the studio",
  rendering: "Rendering",
  done: "Finished",
  error: "Interrupted",
  cancelled: "Set aside",
};

/** A small inked dot and a label, like a gallery's "on loan" tag. */
export function StatusPill({ status, solid }: { status: RunStatus; solid?: boolean }) {
  const active = status === "queued" || status === "planning" || status === "rendering";
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 font-mono text-[10px] font-medium tracking-[0.14em] whitespace-nowrap uppercase",
        status === "done" ? "text-sage" : status === "error" ? "text-brick" : active ? "text-accent" : "text-faint",
        solid && "rounded-[2px] bg-paper/95 px-1.5 py-1 shadow-card",
      )}
    >
      <span className={clsx("size-[5px] rounded-full bg-current", active && "ink-pulse")} />
      {STATUS_LABELS[status]}
    </span>
  );
}
