import clsx from "clsx";

/**
 * "Study for a moving picture": a cubist line composition in charcoal, graphite and sienna.
 * Film frames, a split plane and two mismatched eyes, drawn in with a single continuous line.
 */
export function StudyPlate({ className, animate = true }: { className?: string; animate?: boolean }) {
  const line = clsx(animate && "draw-line");
  return (
    <svg viewBox="0 0 480 560" className={clsx("block", className)} fill="none" aria-hidden>
      {/* canvas and the split plane */}
      <rect x="40" y="30" width="400" height="500" className="fill-paper stroke-line-strong" strokeWidth="1" />
      <path d="M250 30H440V530H150Z" className="fill-active" />
      <path d="M40 360L250 30" className="stroke-line-strong" strokeWidth="1" />

      {/* sun */}
      <circle cx="120" cy="118" r="52" className="stroke-faint" strokeWidth="1" />
      <circle cx="120" cy="118" r="52" className="fill-hover" />

      {/* film frames, slightly off true */}
      <g transform="rotate(-6 270 190)">
        <rect x="150" y="110" width="250" height="160" className="stroke-fg" strokeWidth="1.2" />
        <rect x="160" y="120" width="230" height="140" className="stroke-faint" strokeWidth="0.6" />
      </g>
      <g transform="rotate(5 180 370)">
        <rect x="80" y="300" width="200" height="130" className="stroke-muted" strokeWidth="1" />
      </g>

      {/* a scrap of film stock */}
      <g transform="rotate(-11 380 410)">
        <rect x="300" y="386" width="170" height="48" className="fill-film" />
        {Array.from({ length: 11 }).map((_, i) => (
          <g key={i}>
            <rect x={306 + i * 15} y="390" width="7" height="5" className="fill-paper" opacity="0.55" />
            <rect x={306 + i * 15} y="425" width="7" height="5" className="fill-paper" opacity="0.55" />
          </g>
        ))}
        <rect x="314" y="399" width="44" height="22" className="fill-faint" opacity="0.5" />
        <rect x="364" y="399" width="44" height="22" className="fill-faint" opacity="0.35" />
        <rect x="414" y="399" width="44" height="22" className="fill-faint" opacity="0.22" />
      </g>

      {/* the frontal eye, and its pupil off its socket */}
      <path d="M130 232C175 178 285 178 330 232C285 284 175 284 130 232Z" className={clsx("stroke-fg", line)} strokeWidth="1.6" style={{ ["--len" as string]: 520 }} />
      <circle cx="248" cy="224" r="27" className="fill-accent" />
      <circle cx="240" cy="230" r="27" className="stroke-fg" strokeWidth="1" />

      {/* the profile: one continuous stroke from brow to chin */}
      <path
        d="M318 120C350 170 322 228 362 286C344 304 318 314 336 346C318 368 296 380 262 392C220 406 186 386 186 352C186 330 204 318 222 322"
        className={clsx("stroke-fg", line)}
        strokeWidth="1.5"
        strokeLinecap="round"
        style={{ ["--len" as string]: 760 }}
      />
      {/* the second, smaller eye in profile */}
      <path d="M116 336C136 318 172 318 192 336C172 352 136 352 116 336Z" className="stroke-fg" strokeWidth="1.3" />
      <circle cx="158" cy="335" r="6" className="fill-fg" />
      {/* mouth */}
      <path d="M214 428C240 446 272 444 292 428" className={clsx("stroke-fg", line)} strokeWidth="1.4" strokeLinecap="round" style={{ ["--len" as string]: 120 }} />
      <path d="M232 470L300 470" className="stroke-muted" strokeWidth="1" />
    </svg>
  );
}

/** A quiet monochrome scene used to preview styles: the grade and captions change on top of it. */
export function SceneSwatch({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" className={clsx("block", className)} style={style} aria-hidden>
      <defs>
        <linearGradient id="swatch-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#cfc6b4" />
          <stop offset="0.6" stopColor="#a49a88" />
          <stop offset="1" stopColor="#6d665b" />
        </linearGradient>
      </defs>
      <rect width="320" height="180" fill="url(#swatch-sky)" />
      <circle cx="236" cy="52" r="20" fill="#efe7d6" opacity="0.85" />
      <path d="M0 128L52 92L96 112L150 70L204 104L250 84L320 110V180H0Z" fill="#4f4942" />
      <path d="M0 150L70 122L128 140L188 116L250 136L320 124V180H0Z" fill="#2d2a26" />
      <path d="M150 70L174 180H118Z" fill="#5c564d" opacity="0.7" />
      <path d="M0 0L120 0L0 96Z" fill="#ffffff" opacity="0.07" />
    </svg>
  );
}
