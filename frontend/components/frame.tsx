import clsx from "clsx";
import { ReactNode } from "react";

/** A matted frame on the wall: hairline edge, paper mat, the work inset. */
export function Frame({ children, className, ratio = "aspect-[4/3]" }: { children: ReactNode; className?: string; ratio?: string }) {
  return (
    <div className={clsx("border border-line bg-paper p-2.5 shadow-card transition-shadow duration-500 group-hover:shadow-pop", className)}>
      <div className={clsx("relative overflow-hidden bg-soft", ratio)}>{children}</div>
    </div>
  );
}

/** Empty canvas for a work with no materials yet. */
export function BlankCanvas({ label }: { label?: string }) {
  return (
    <div className="absolute inset-0">
      <svg viewBox="0 0 100 75" preserveAspectRatio="none" className="absolute inset-0 size-full" aria-hidden>
        <path d="M58 0H100V75H38Z" className="fill-hover" />
        <path d="M0 60L58 0" className="stroke-line-strong" strokeWidth="0.3" vectorEffect="non-scaling-stroke" />
      </svg>
      {label && (
        <span className="absolute inset-0 flex items-center justify-center text-[13px] text-faint">{label}</span>
      )}
    </div>
  );
}
