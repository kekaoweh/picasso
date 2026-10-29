export type User = { id: string; name: string; token_kind: "oauth" | "api_key"; token_hint: string };

export type AssetKind = "video" | "image" | "audio";
export type AssetRole = "footage" | "reference" | "music";
export type Aspect = "16:9" | "9:16" | "1:1" | "4:5";
export type RunStatus = "queued" | "planning" | "rendering" | "done" | "error" | "cancelled";

export type Asset = {
  id: string;
  kind: AssetKind;
  role: AssetRole;
  name: string;
  duration: number | null;
  width: number | null;
  height: number | null;
  has_audio: boolean;
  note: string;
  has_thumb: boolean;
  /** "upload", or the footage library the editor found it in. */
  source: string;
  source_url: string;
  credit: string;
  license: string;
  created_at: string;
};

export type FootageSource = { name: string; kinds: AssetKind[]; enabled: boolean; needs_key: string | null };

export type Run = {
  id: string;
  project_id: string;
  instruction: string;
  mode: "agent" | "render";
  status: RunStatus;
  error: string | null;
  has_video: boolean;
  duration: number | null;
  cost_usd: number | null;
  created_at: string;
  finished_at: string | null;
};

export type TextOverlay = {
  text: string;
  position?: "top" | "center" | "bottom" | "lower_third" | null;
  style?: "caption" | "title" | "subtitle";
};

export type Clip = {
  kind: "asset" | "title_card";
  asset_id?: string | null;
  source_start: number;
  duration: number;
  text?: TextOverlay | null;
  motion: string;
  background: string;
  transition?: "cut" | "fade" | null;
  keep_audio: boolean;
  note: string;
};

export type Timeline = {
  title: string;
  clips: Clip[];
  music?: { asset_id: string; volume: number; start_at: number } | null;
};

export type ProjectSummary = {
  id: string;
  name: string;
  emoji: string;
  aspect: Aspect;
  target_seconds: number;
  style_id: string | null;
  cover_asset_id: string | null;
  latest_status: RunStatus | null;
  created_at: string;
  updated_at: string;
};

export type Project = ProjectSummary & {
  prompt: string;
  script: string;
  timeline: Timeline | null;
  assets: Asset[];
  latest_run: Run | null;
};

export type Style = {
  id: string;
  name: string;
  emoji: string;
  description: string;
  pacing_seconds: number;
  caption_position: "top" | "center" | "bottom" | "lower_third";
  caption_color: string;
  caption_box: boolean;
  transition: "cut" | "fade";
  brightness: number;
  contrast: number;
  saturation: number;
  builtin: boolean;
};

export type StyleInput = Omit<Style, "id" | "builtin">;

export type RunEvent = {
  id: number;
  type: "status" | "message" | "tool" | "progress" | "error";
  at: string;
  status?: RunStatus;
  error?: string;
  text?: string;
  name?: string;
  label?: string;
  input?: Record<string, unknown>;
  done?: number;
  total?: number;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(`/api${path}`, { ...init, headers, credentials: "include" });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    if (res.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  login: (token: string, name: string) =>
    request<User>("/auth/login", { method: "POST", body: json({ token, name }) }),
  me: () => request<User>("/auth/me"),
  updateMe: (name: string) => request<User>("/auth/me", { method: "PATCH", body: json({ name }) }),
  logout: () => request("/auth/logout", { method: "POST" }),
  forget: () => request("/auth/forget", { method: "POST" }),

  projects: () => request<ProjectSummary[]>("/projects"),
  project: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (body: Partial<Project>) =>
    request<Project>("/projects", { method: "POST", body: json(body) }),
  updateProject: (id: string, body: Partial<Project>, keepalive = false) =>
    request<Project>(`/projects/${id}`, { method: "PATCH", body: json(body), keepalive }),
  deleteProject: (id: string) => request(`/projects/${id}`, { method: "DELETE" }),

  updateAsset: (id: string, body: Partial<Asset>) =>
    request<Asset>(`/assets/${id}`, { method: "PATCH", body: json(body) }),
  deleteAsset: (id: string) => request(`/assets/${id}`, { method: "DELETE" }),

  styles: () => request<Style[]>("/styles"),
  sources: () => request<FootageSource[]>("/sources"),
  createStyle: (body: StyleInput) => request<Style>("/styles", { method: "POST", body: json(body) }),
  updateStyle: (id: string, body: StyleInput) =>
    request<Style>(`/styles/${id}`, { method: "PUT", body: json(body) }),
  deleteStyle: (id: string) => request(`/styles/${id}`, { method: "DELETE" }),

  runs: (projectId: string) => request<Run[]>(`/projects/${projectId}/runs`),
  startRun: (projectId: string, instruction: string, mode: "agent" | "render" = "agent") =>
    request<Run>(`/projects/${projectId}/runs`, { method: "POST", body: json({ instruction, mode }) }),
  run: (id: string) => request<Run>(`/runs/${id}`),
  cancelRun: (id: string) => request<Run>(`/runs/${id}/cancel`, { method: "POST" }),
};

/** Upload with progress (fetch can't report upload progress). */
export function uploadAssets(
  projectId: string,
  files: File[],
  onProgress: (fraction: number) => void,
): Promise<Asset[]> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/projects/${projectId}/assets`);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body: { detail?: string } | Asset[] = [];
      try {
        body = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Asset[]);
      else reject(new ApiError(xhr.status, (body as { detail?: string }).detail || "Upload failed"));
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    xhr.send(form);
  });
}

export const media = {
  thumb: (assetId: string) => `/api/assets/${assetId}/thumb`,
  file: (assetId: string) => `/api/assets/${assetId}/file`,
  video: (runId: string, download = false) => `/api/runs/${runId}/video${download ? "?download=true" : ""}`,
  events: (runId: string) => `/api/runs/${runId}/events`,
};

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  return `${m}:${String(r).padStart(2, "0")}`;
}

export function formatLength(seconds: number): string {
  if (seconds < 60) return `${seconds} sec`;
  const m = Math.floor(seconds / 60);
  const r = seconds % 60;
  return r ? `${m} min ${r} sec` : `${m} min`;
}

export function timeAgo(iso: string): string {
  const then = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").getTime();
  const diff = Math.max(0, Date.now() - then) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(then).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export const ACTIVE_STATUSES: RunStatus[] = ["queued", "planning", "rendering"];
