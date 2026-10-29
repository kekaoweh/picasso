import clsx from "clsx";
import { useId } from "react";

/**
 * Picasso's mark: a cubist eye. A square plane split on the diagonal; the eye's outline
 * changes ink as it crosses the split, and the pupil sits slightly off its socket.
 */
export function Logo({ className }: { className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 40 40" className={clsx("shrink-0", className)} aria-hidden>
      <defs>
        <clipPath id={`${id}-dark`}>
          <path d="M0 0H40L0 40Z" />
        </clipPath>
        <clipPath id={`${id}-light`}>
          <path d="M40 0V40H0Z" />
        </clipPath>
      </defs>
      <rect x="0.75" y="0.75" width="38.5" height="38.5" className="fill-paper stroke-fg" strokeWidth="1.5" />
      <path d="M0 0H40L0 40Z" className="fill-fg" />
      <g fill="none" strokeWidth="1.6" strokeLinecap="round">
        <path d="M6 21C12 12 28 12 34 21C28 29 12 29 6 21Z" clipPath={`url(#${id}-dark)`} className="stroke-paper" />
        <path d="M6 21C12 12 28 12 34 21C28 29 12 29 6 21Z" clipPath={`url(#${id}-light)`} className="stroke-fg" />
      </g>
      <circle cx="22.5" cy="19" r="4.2" className="fill-accent" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2.5", className)}>
      <Logo className="size-7" />
      <span className="font-display text-[24px] leading-none tracking-tight italic">Picasso</span>
    </span>
  );
}
