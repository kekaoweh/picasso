"use client";

import clsx from "clsx";
import { LogOut, PanelLeftClose, Pencil, Plus, ShieldOff } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useApp } from "@/components/app-context";
import { Wordmark } from "@/components/logo";
import { Menu, MenuItem, plate } from "@/components/ui";
import { ACTIVE_STATUSES, api } from "@/lib/api";

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const { user, setUser, projects, refreshProjects, plateOf } = useApp();
  const pathname = usePathname();
  const router = useRouter();
  const [creating, setCreating] = useState(false);

  const newWork = async () => {
    setCreating(true);
    try {
      const p = await api.createProject({ name: "Untitled" });
      await refreshProjects();
      router.push(`/projects/${p.id}`);
      onClose?.();
    } finally {
      setCreating(false);
    }
  };

  const rename = async () => {
    const name = window.prompt("Studio name", user.name);
    if (name?.trim()) setUser(await api.updateMe(name.trim()));
  };

  const signOut = async () => {
    await api.logout();
    window.location.href = "/login";
  };

  const forget = async () => {
    if (!window.confirm("Sign out everywhere and delete your stored Claude token? Your works stay.")) return;
    await api.forget();
    window.location.href = "/login";
  };

  return (
    <aside className="flex h-full w-[248px] flex-col bg-soft">
      <div className="flex items-center justify-between px-5 pt-5 pb-6">
        <Link href="/" onClick={onClose} aria-label="Picasso home">
          <Wordmark />
        </Link>
        {onClose && (
          <button onClick={onClose} className="rounded-[2px] p-1.5 text-faint hover:bg-hover hover:text-fg" aria-label="Close sidebar">
            <PanelLeftClose className="size-4" strokeWidth={1.5} />
          </button>
        )}
      </div>

      <nav className="space-y-0.5 px-3">
        <NavLink href="/" active={pathname === "/"} onClick={onClose}>Studio</NavLink>
        <NavLink href="/styles" active={pathname === "/styles"} onClick={onClose}>Styles</NavLink>
      </nav>

      <div className="mt-8 flex items-center justify-between px-5 pb-2">
        <span className="label">The collection</span>
        <button onClick={newWork} disabled={creating} className="rounded-[2px] p-0.5 text-faint hover:text-fg" aria-label="New work">
          <Plus className="size-3.5" strokeWidth={1.5} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {projects.length === 0 && (
          <p className="px-2 py-1 text-[13px] text-faint">Nothing on the walls yet.</p>
        )}
        {projects.map((p) => {
          const active = pathname === `/projects/${p.id}`;
          const working = p.latest_status && ACTIVE_STATUSES.includes(p.latest_status);
          return (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              onClick={onClose}
              className={clsx(
                "group relative flex items-baseline gap-2.5 rounded-[2px] py-1.5 pr-2 pl-3 transition-colors",
                active ? "bg-active text-fg" : "text-muted hover:bg-hover hover:text-fg",
              )}
            >
              {active && <span className="absolute top-1.5 bottom-1.5 left-0 w-[2px] bg-accent" />}
              <span className="w-11 shrink-0 font-mono text-[10px] tracking-wider whitespace-nowrap text-faint">{plate(plateOf(p.id))}</span>
              <span className="min-w-0 flex-1 truncate text-[13.5px]">{p.name || "Untitled"}</span>
              {working && <span className="ink-pulse size-[5px] shrink-0 self-center rounded-full bg-accent" title="In the studio" />}
            </Link>
          );
        })}
      </div>

      <div className="space-y-3 border-t border-line px-3 pt-3 pb-4">
        <button
          onClick={newWork}
          disabled={creating}
          className="flex h-9 w-full items-center justify-center gap-2 rounded-[3px] border border-line-strong bg-paper text-[13px] font-medium text-fg transition-colors hover:border-fg/40"
        >
          <Plus className="size-3.5" strokeWidth={1.5} />
          Begin a new work
        </button>
        <Menu
          width="w-60"
          trigger={({ toggle }) => (
            <button onClick={toggle} className="flex w-full items-center gap-2.5 rounded-[2px] px-2 py-1.5 text-left hover:bg-hover">
              <span className="flex size-7 shrink-0 items-center justify-center border border-line-strong text-[13px] font-semibold text-fg">
                {user.name.slice(0, 1).toUpperCase()}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[13px] font-medium">{user.name}</span>
                <span className="block font-mono text-[10px] tracking-wider text-faint">
                  {user.token_kind === "oauth" ? "CLAUDE ACCOUNT" : "API KEY"}
                </span>
              </span>
            </button>
          )}
        >
          {(close) => (
            <>
              <div className="px-2.5 pt-2 pb-2">
                <div className="label">Connected</div>
                <div className="mt-1 font-mono text-[11px] text-muted">{user.token_hint}</div>
              </div>
              <div className="my-1 h-px bg-line" />
              <MenuItem icon={<Pencil className="size-3.5" strokeWidth={1.5} />} onClick={() => { close(); rename(); }}>
                Rename studio
              </MenuItem>
              <MenuItem icon={<LogOut className="size-3.5" strokeWidth={1.5} />} onClick={signOut}>
                Sign out
              </MenuItem>
              <MenuItem icon={<ShieldOff className="size-3.5" strokeWidth={1.5} />} onClick={forget} danger>
                Disconnect Claude
              </MenuItem>
            </>
          )}
        </Menu>
      </div>
    </aside>
  );
}

function NavLink({ href, active, children, onClick }: { href: string; active: boolean; children: React.ReactNode; onClick?: () => void }) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={clsx(
        "relative flex items-center rounded-[2px] py-1.5 pl-3 text-[14px] font-medium transition-colors",
        active ? "text-fg" : "text-muted hover:text-fg",
      )}
    >
      {active && <span className="absolute top-2 bottom-2 left-0 w-[2px] bg-accent" />}
      {children}
    </Link>
  );
}
