"use client";

import { Menu as MenuIcon } from "lucide-react";
import { useState } from "react";
import { AppProvider } from "@/components/app-context";
import { Logo, Wordmark } from "@/components/logo";
import { Sidebar } from "@/components/sidebar";
import { Spinner } from "@/components/ui";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <AppProvider
      fallback={
        <div className="flex h-dvh flex-col items-center justify-center gap-4 text-faint">
          <Logo className="size-9" />
          <Spinner />
        </div>
      }
    >
      <div className="flex h-dvh overflow-hidden">
        <div className="hidden border-r border-line md:block">
          <Sidebar />
        </div>
        {mobileOpen && (
          <div className="fixed inset-0 z-40 md:hidden">
            <div className="absolute inset-0 bg-fg/25" onClick={() => setMobileOpen(false)} />
            <div className="fade-up relative h-full w-[248px] shadow-pop">
              <Sidebar onClose={() => setMobileOpen(false)} />
            </div>
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-4 md:hidden">
            <button onClick={() => setMobileOpen(true)} className="rounded-[2px] p-1.5 hover:bg-hover" aria-label="Open sidebar">
              <MenuIcon className="size-4" strokeWidth={1.5} />
            </button>
            <Wordmark />
          </header>
          <div className="min-h-0 flex-1">{children}</div>
        </div>
      </div>
    </AppProvider>
  );
}
