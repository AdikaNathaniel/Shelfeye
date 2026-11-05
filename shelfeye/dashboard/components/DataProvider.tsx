"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { DashboardData, UnauthorizedError, User, fetchDashboard, fetchMe, logout, shelfName } from "@/lib/api";

const REFRESH_MS = 10000;

export type Connection = "connecting" | "live" | "offline";

type Shared = {
  user: User;
  data: DashboardData | null;
  connection: Connection;
  updatedAt: Date | null;
  signOut: () => Promise<void>;
  /** Fetch fresh data now, e.g. right after changing a setting. */
  refresh: () => Promise<void>;
};

const DataContext = createContext<Shared | null>(null);

export function useShelfEye() {
  const value = useContext(DataContext);
  if (!value) throw new Error("useShelfEye must be used inside <DataProvider>");
  return value;
}

/** Turns a camera ID into the name of its shelf from Settings. */
export function useShelfName() {
  const shelves = useShelfEye().data?.shelves ?? [];
  return (nodeId: string) => shelfName(nodeId, shelves);
}

export default function DataProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const refreshRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    let cancelled = false;

    async function toLogin() {
      await logout(); // clears an expired cookie so the login page doesn't bounce back
      router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }

    async function refresh() {
      try {
        const next = await fetchDashboard();
        if (cancelled) return;
        setData(next);
        setConnection("live");
        setUpdatedAt(new Date());
      } catch (err) {
        if (cancelled) return;
        if (err instanceof UnauthorizedError) return toLogin();
        setConnection("offline"); // keep showing the last data we had
      }
    }

    refreshRef.current = refresh;
    fetchMe()
      .then((me) => {
        if (cancelled) return;
        setUser(me);
        refresh();
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof UnauthorizedError) toLogin();
        else setConnection("offline");
      });

    const timer = setInterval(refresh, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [router]);

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  if (!user) {
    return (
      <div className="loading-screen">
        {connection === "offline" ? "Can't reach the ShelfEye server. Retrying…" : "Loading ShelfEye…"}
      </div>
    );
  }

  return (
    <DataContext.Provider value={{ user, data, connection, updatedAt, signOut, refresh: () => refreshRef.current() }}>{children}</DataContext.Provider>
  );
}
