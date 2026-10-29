"use client";

import clsx from "clsx";
import { ButtonHTMLAttributes, forwardRef, ReactNode, useEffect, useRef, useState } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-[3px] font-medium whitespace-nowrap transition-[background,color,opacity,border-color] duration-200 select-none",
        "disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-fg",
        size === "sm" && "h-7 px-2.5 text-[12.5px]",
        size === "md" && "h-9 px-3.5 text-[13.5px]",
        size === "lg" && "h-11 px-5 text-[14.5px] tracking-[0.01em]",
        variant === "primary" && "bg-fg text-bg hover:bg-fg/85",
        variant === "secondary" && "border border-line-strong bg-paper text-fg hover:border-fg/40",
        variant === "ghost" && "text-muted hover:bg-hover hover:text-fg",
        variant === "danger" && "text-red hover:bg-red-soft",
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
});

/** Three ink dots, drawn in turn. */
export function Spinner({ className }: { className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-[3px]", className)} role="status" aria-label="Loading">
      {[0, 1, 2].map((i) => (
        <span key={i} className="ink-pulse size-[4px] rounded-full bg-current" style={{ animationDelay: `${i * 0.2}s` }} />
      ))}
    </span>
  );
}

export function Pill({
  children,
  tone = "gray",
  className,
}: {
  children: ReactNode;
  tone?: "gray" | "blue" | "green" | "red" | "accent";
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 font-mono text-[10.5px] font-medium tracking-[0.12em] whitespace-nowrap uppercase",
        tone === "gray" && "text-faint",
        tone === "blue" && "text-blue",
        tone === "green" && "text-green",
        tone === "red" && "text-red",
        tone === "accent" && "text-accent",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Popover anchored to its trigger: a sheet of paper with a hairline edge. */
export function Menu({
  trigger,
  children,
  align = "left",
  width = "w-56",
}: {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
  width?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={ref} className="relative inline-block">
      {trigger({ open, toggle: () => setOpen((o) => !o) })}
      {open && (
        <div
          className={clsx(
            "fade-up absolute z-50 mt-1.5 rounded-[3px] bg-paper p-1 shadow-pop",
            width,
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export function MenuItem({
  children,
  onClick,
  active,
  icon,
  hint,
  danger,
}: {
  children: ReactNode;
  onClick: () => void;
  active?: boolean;
  icon?: ReactNode;
  hint?: ReactNode;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "flex w-full items-center gap-2.5 rounded-[2px] px-2.5 py-1.5 text-left text-[13.5px] transition-colors hover:bg-hover",
        active && "bg-hover",
        danger ? "text-red" : "text-fg",
      )}
    >
      {icon && <span className="flex w-4 shrink-0 justify-center text-faint">{icon}</span>}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {hint && <span className="shrink-0 font-mono text-[10.5px] tracking-wider text-faint">{hint}</span>}
    </button>
  );
}

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
export const roman = (n: number) => ROMAN[n - 1] ?? String(n);

/** Catalogue-style section heading: "II — Preview" over a hairline. */
export function SectionTitle({ n, children, action }: { n?: number; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-baseline gap-3 border-b border-line pb-2">
      {n !== undefined && <span className="font-mono text-[11px] leading-none text-faint">{roman(n)}.</span>}
      <h2 className="label !text-muted">{children}</h2>
      {action && <div className="ml-auto">{action}</div>}
    </div>
  );
}

/** A catalogue number like "No. 07". */
export const plate = (n: number) => `No. ${String(n).padStart(2, "0")}`;

export function useDebouncedCallback<A extends unknown[]>(fn: (...args: A) => void, ms: number) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef(fn);
  latest.current = fn;
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  return (...args: A) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => latest.current(...args), ms);
  };
}

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);
    const onChange = () => setMatches(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}
