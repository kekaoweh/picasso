"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ProjectSummary, Style, User } from "@/lib/api";

type AppState = {
  user: User;
  setUser: (u: User) => void;
  projects: ProjectSummary[];
  refreshProjects: () => Promise<void>;
  patchProjectSummary: (id: string, patch: Partial<ProjectSummary>) => void;
  /** Catalogue number for a work, in the order works were begun. */
  plateOf: (id: string) => number;
  styles: Style[];
  refreshStyles: () => Promise<void>;
};

const Ctx = createContext<AppState | null>(null);

export function useApp() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp outside AppProvider");
  return ctx;
}

export function AppProvider({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [styles, setStyles] = useState<Style[]>([]);

  const refreshProjects = useCallback(async () => setProjects(await api.projects()), []);
  const refreshStyles = useCallback(async () => setStyles(await api.styles()), []);
  const patchProjectSummary = useCallback(
    (id: string, patch: Partial<ProjectSummary>) =>
      setProjects((ps) => ps.map((p) => (p.id === id ? { ...p, ...patch } : p))),
    [],
  );

  const plates = useMemo(() => {
    const ordered = [...projects].sort((a, b) => a.created_at.localeCompare(b.created_at));
    return new Map(ordered.map((p, i) => [p.id, i + 1]));
  }, [projects]);
  const plateOf = useCallback((id: string) => plates.get(id) ?? plates.size + 1, [plates]);

  useEffect(() => {
    // api.request redirects to /login on 401.
    api.me().then(async (u) => {
      setUser(u);
      await Promise.all([refreshProjects(), refreshStyles()]);
    }).catch(() => {});
  }, [refreshProjects, refreshStyles]);

  if (!user) return <>{fallback}</>;
  return (
    <Ctx.Provider value={{ user, setUser, projects, refreshProjects, patchProjectSummary, plateOf, styles, refreshStyles }}>
      {children}
    </Ctx.Provider>
  );
}
