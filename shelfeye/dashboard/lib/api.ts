// Types and helpers for the ShelfEye server API (see server/app.py and server/auth.py).
// Ids are MongoDB ids, so they are strings.

export type InventoryRow = {
  node_id: string;
  name: string;
  count: number;
  label_text: string;
  updated_at: string;
};

export type StockEvent = {
  id: string;
  node_id: string;
  name: string;
  previous: number;
  current: number;
  delta: number;
  captured_at: string;
};

export type ShelfNode = {
  node_id: string;
  last_seen: string;
  live_view: boolean; // the camera relays a live view through the server
};

/** A shelf set up on the Settings page, optionally watched by one camera. */
export type Shelf = {
  id: string;
  name: string;
  node_id: string | null;
  created_at: string;
};

export type DashboardData = {
  inventory: InventoryRow[];
  events: StockEvent[];
  nodes: ShelfNode[];
  shelves: Shelf[];
};

export type User = {
  id: string; // MongoDB id
  name: string;
  email: string;
};

export const LOW_STOCK = 2; // counts at or below this are "Low"
export const STALE_MINUTES = 35; // cameras re-count every 30 min, so silence beyond this is a problem
export const LIVE_VIEW_MAX_MINUTES = 10; // matches LIVE_VIEW_MAX_MINUTES on the Pi

/** Thrown when the session is missing or expired, so the app can send the user to the login page. */
export class UnauthorizedError extends Error {}

async function errorMessage(response: Response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {}
  return response.status >= 500 ? "The ShelfEye server isn't responding. Please try again." : "Please check the form and try again.";
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

async function sendJson<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401 && !path.startsWith("/api/auth/")) throw new UnauthorizedError();
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.status === 204 ? (undefined as T) : response.json();
}

const postJson = <T>(path: string, body?: unknown) => sendJson<T>("POST", path, body);

export async function fetchDashboard(): Promise<DashboardData> {
  const [inventory, events, nodes, shelves] = await Promise.all([
    getJson<InventoryRow[]>("/api/inventory"),
    getJson<StockEvent[]>("/api/events?limit=500"),
    getJson<ShelfNode[]>("/api/nodes"),
    getJson<Shelf[]>("/api/shelves"),
  ]);
  return { inventory, events, nodes, shelves };
}

export const createShelf = (name: string, node_id: string | null) => postJson<Shelf>("/api/shelves", { name, node_id });
export const updateShelf = (id: string, changes: { name?: string; node_id?: string | null }) =>
  sendJson<Shelf>("PATCH", `/api/shelves/${id}`, changes);
export const deleteShelf = (id: string) => sendJson<void>("DELETE", `/api/shelves/${id}`);

/** Settings the cameras pick up on their next heartbeat (within 5 minutes). */
export type Settings = {
  keep_images_days: number;
};

export const MAX_KEEP_IMAGES_DAYS = 3650; // matches server/settings.py
export const fetchSettings = () => getJson<Settings>("/api/settings");
export const updateSettings = (changes: Partial<Settings>) => sendJson<Settings>("PATCH", "/api/settings", changes);

/** The shelf name for a camera, or the camera ID when no shelf is assigned to it. */
export function shelfName(nodeId: string, shelves: Shelf[]) {
  return shelves.find((s) => s.node_id === nodeId)?.name ?? nodeId;
}

/** Every camera ID the dashboard knows about: checked-in cameras plus any that sent stock. */
export function knownCameras(data: DashboardData) {
  return [...new Set([...data.nodes.map((n) => n.node_id), ...data.inventory.map((r) => r.node_id)])].sort();
}

export const fetchMe = () => getJson<User>("/api/auth/me");
export const login = (email: string, password: string) => postJson<User>("/api/auth/login", { email, password });
export const register = (name: string, email: string, password: string) =>
  postJson<User>("/api/auth/register", { name, email, password });
export const logout = () => postJson("/api/auth/logout").catch(() => undefined);

export function minutesAgo(iso: string) {
  return (Date.now() - new Date(iso).getTime()) / 60000;
}

export function timeAgo(iso: string) {
  const mins = minutesAgo(iso);
  if (mins < 1) return "just now";
  if (mins < 60) return `${Math.floor(mins)} min ago`;
  if (mins < 24 * 60) return `${Math.floor(mins / 60)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function clockTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function dayLabel(iso: string) {
  const day = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (day.toDateString() === today.toDateString()) return "Today";
  if (day.toDateString() === yesterday.toDateString()) return "Yesterday";
  return day.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

export function isToday(iso: string) {
  return new Date(iso).toDateString() === new Date().toDateString();
}

export function isReporting(node: ShelfNode) {
  return minutesAgo(node.last_seen) <= STALE_MINUTES;
}

export type StockLevel = "ok" | "low" | "out";

export function stockLevel(count: number): StockLevel {
  if (count === 0) return "out";
  if (count <= LOW_STOCK) return "low";
  return "ok";
}

export const STOCK_LABEL: Record<StockLevel, string> = { ok: "In stock", low: "Low", out: "Out of stock" };
