"use client";

import { ArrowRight, Check, Copy, Eye, EyeOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { StudyPlate } from "@/components/artwork";
import { Wordmark } from "@/components/logo";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";

const COMMAND = "claude setup-token";

export default function LoginPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.me().then(() => router.replace("/")).catch(() => {});
  }, [router]);

  const copy = async () => {
    await navigator.clipboard.writeText(COMMAND);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(token.trim(), name.trim());
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setBusy(false);
    }
  };

  const looksValid = /^sk-ant-(oat|api)/.test(token.trim());

  return (
    <main className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      {/* The plate */}
      <section className="relative hidden flex-col justify-between border-r border-line bg-soft px-14 py-12 lg:flex">
        <Wordmark />
        <figure className="mx-auto w-full max-w-[440px]">
          <StudyPlate className="w-full" />
          <figcaption className="mt-5 flex items-baseline justify-between gap-6 border-t border-line pt-3">
            <span className="label">Plate I</span>
            <span className="text-right">
              <span className="block text-[14px] font-medium">Study for a moving picture</span>
              <span className="block text-[12px] text-faint">Charcoal and sienna on gesso, 2026</span>
            </span>
          </figcaption>
        </figure>
        <blockquote className="max-w-[420px]">
          <p className="text-[21px] leading-[1.35] font-medium tracking-[-0.015em] text-muted">
            “I begin with an idea, and then it becomes something else.”
          </p>
          <footer className="label mt-3">Pablo Picasso</footer>
        </blockquote>
      </section>

      {/* The door */}
      <section className="flex flex-col justify-center px-6 py-14 sm:px-14">
        <div className="mx-auto w-full max-w-[420px]">
          <div className="mb-10 lg:hidden">
            <Wordmark />
          </div>
          <p className="label">A studio for moving pictures</p>
          <h1 className="mt-3 text-[40px] leading-[1.04] font-semibold tracking-[-0.04em]">
            Describe the film.<br />
            <span className="text-muted">We&apos;ll make it.</span>
          </h1>
          <p className="mt-4 text-[15px] leading-relaxed text-muted">
            Describe it in a sentence or a page. Picasso researches the subject, finds licensed footage, writes the piece and cuts it, frame by frame.
          </p>

          <form onSubmit={submit} className="mt-10">
            <p className="label mb-6 border-b border-line pb-2">Sign in with your Claude account</p>
            <ol className="space-y-7">
              <Step n="I" title="In your terminal, run">
                <div className="mt-2.5 flex items-center gap-3 border border-line-strong bg-paper py-2 pr-2 pl-3.5">
                  <code className="flex-1 font-mono text-[13px] select-all">{COMMAND}</code>
                  <button
                    type="button"
                    onClick={copy}
                    className="rounded-[2px] p-1.5 text-faint transition-colors hover:bg-hover hover:text-fg"
                    aria-label="Copy command"
                  >
                    {copied ? <Check className="size-3.5 text-sage" strokeWidth={1.5} /> : <Copy className="size-3.5" strokeWidth={1.5} />}
                  </button>
                </div>
                <p className="mt-2 text-[13px] leading-relaxed text-faint">
                  It opens Claude in your browser, then prints a long-lived token.
                </p>
              </Step>

              <Step n="II" title="Paste the token">
                <div className="relative mt-1">
                  <input
                    type={show ? "text" : "password"}
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="sk-ant-oat01-…"
                    autoComplete="off"
                    spellCheck={false}
                    autoFocus
                    className="h-10 w-full border-b border-line-strong bg-transparent pr-8 font-mono text-[13px] outline-none placeholder:text-faint focus:border-fg"
                  />
                  <button
                    type="button"
                    onClick={() => setShow((s) => !s)}
                    className="absolute top-1/2 right-0 -translate-y-1/2 p-1 text-faint hover:text-fg"
                    aria-label={show ? "Hide token" : "Show token"}
                  >
                    {show ? <EyeOff className="size-3.5" strokeWidth={1.5} /> : <Eye className="size-3.5" strokeWidth={1.5} />}
                  </button>
                </div>
              </Step>

              <Step n="III" title="Name your studio" optional>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Teddy's studio"
                  maxLength={80}
                  className="mt-1 h-10 w-full border-b border-line-strong bg-transparent text-[15px] outline-none placeholder:text-faint focus:border-fg"
                />
              </Step>
            </ol>

            {error && (
              <p className="mt-6 border-l-2 border-brick bg-brick-soft px-3.5 py-2.5 text-[13px] leading-relaxed text-brick">{error}</p>
            )}

            <Button type="submit" variant="primary" size="lg" className="mt-9 w-full" loading={busy} disabled={!looksValid}>
              {busy ? "Checking with Claude" : "Enter the studio"}
              {!busy && <ArrowRight className="size-4" strokeWidth={1.5} />}
            </Button>
          </form>

          <p className="mt-8 text-[12px] leading-relaxed text-faint">
            Your token is encrypted at rest and only used to run your own editor. No Claude Code yet?{" "}
            <code className="font-mono">npm i -g @anthropic-ai/claude-code</code>. An Anthropic API key (
            <code className="font-mono">sk-ant-api…</code>) works here too.
          </p>
        </div>
      </section>
    </main>
  );
}

function Step({ n, title, optional, children }: { n: string; title: string; optional?: boolean; children: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[34px_1fr] gap-x-2">
      <span className="font-mono text-[11px] leading-[22px] text-faint">{n}.</span>
      <div>
        <div className="text-[14px] leading-[22px] font-medium">
          {title}
          {optional && <span className="ml-2 font-normal text-faint">optional</span>}
        </div>
        {children}
      </div>
    </li>
  );
}
