"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { LOW_STOCK } from "@/lib/api";
import { useShelfEye } from "./DataProvider";
import {
  ActivityIcon, BoxIcon, CameraIcon, LogOutIcon, Logo, OverviewIcon, SettingsIcon, SidebarCollapseIcon, SidebarExpandIcon,
} from "./Icons";

const NAV = [
  { href: "/", label: "Overview", icon: OverviewIcon },
  { href: "/inventory", label: "Inventory", icon: BoxIcon },
  { href: "/activity", label: "Activity", icon: ActivityIcon },
  { href: "/cameras", label: "Cameras", icon: CameraIcon },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

const COLLAPSED_KEY = "shelfeye.sidebarCollapsed";

const PAGE_INFO: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "Overview", subtitle: "Stock levels across all your shelves" },
  "/inventory": { title: "Inventory", subtitle: "Every product the cameras can see" },
  "/activity": { title: "Activity", subtitle: "Items taken and added, as the cameras saw them" },
  "/cameras": { title: "Cameras", subtitle: "Your shelf cameras and live view" },
  "/settings": { title: "Settings", subtitle: "Shelves and your account" },
};

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join("");
}

function Brand() {
  return (
    <Link href="/" className="brand">
      <Logo />
      <div>
        <div className="brand-name">ShelfEye</div>
        <div className="brand-sub">Smart shelf counting</div>
      </div>
    </Link>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, data, connection, updatedAt, signOut } = useShelfEye();
  const lowCount = data ? data.inventory.filter((r) => r.count <= LOW_STOCK).length : 0;
  const page = PAGE_INFO[pathname] ?? PAGE_INFO["/"];
  const [collapsed, setCollapsed] = useState(false);

  // Remembered per browser. Read after mounting so the server-rendered HTML matches.
  useEffect(() => {
    try {
      if (localStorage.getItem(COLLAPSED_KEY) === "1") setCollapsed(true);
    } catch {}
  }, []);

  function toggleSidebar() {
    setCollapsed((was) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, was ? "0" : "1");
      } catch {}
      return !was;
    });
  }

  const links = (className: string) =>
    NAV.map(({ href, label, icon: NavIcon }) => (
      <Link
        key={href}
        href={href}
        className={pathname === href ? `${className} active` : className}
        aria-current={pathname === href ? "page" : undefined}
        title={collapsed && className !== "tab" ? label : undefined}
      >
        <NavIcon size={className === "tab" ? 20 : 18} />
        <span className="nav-text">{label}</span>
        {href === "/inventory" && lowCount > 0 && <span className="count" aria-label={`${lowCount} low`}>{lowCount}</span>}
      </Link>
    ));

  return (
    <div className={collapsed ? "shell collapsed" : "shell"}>
      <aside className="sidebar">
        <div className="sidebar-head">
          <Brand />
          <button
            className="icon-btn collapse-btn"
            onClick={toggleSidebar}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
          >
            {collapsed ? <SidebarExpandIcon /> : <SidebarCollapseIcon />}
          </button>
        </div>
        <div className="nav-label">Menu</div>
        <nav className="nav">{links("")}</nav>
        <div className="user-card">
          <div className="avatar" title={collapsed ? user.name : undefined}>{initials(user.name)}</div>
          <div className="user-name">{user.name}</div>
          <button className="icon-btn" onClick={signOut} title="Log out" aria-label="Log out">
            <LogOutIcon />
          </button>
        </div>
      </aside>

      <div className="main">
        <div className="mobile-bar">
          <Brand />
          <button className="icon-btn" onClick={signOut} title="Log out" aria-label="Log out">
            <LogOutIcon />
          </button>
        </div>

        <header className="topbar">
          <div>
            <h1>{page.title}</h1>
            <p>{page.subtitle}</p>
          </div>
          <div className="status">
            <span className={`dot ${connection === "live" ? "pulse" : connection === "offline" ? "off" : "wait"}`} />
            {connection === "live" && updatedAt && <><strong>Live</strong> · updated {updatedAt.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" })}</>}
            {connection === "connecting" && "Connecting…"}
            {connection === "offline" && <strong>Server unreachable, retrying…</strong>}
          </div>
        </header>

        <main className="content">{children}</main>
      </div>

      <nav className="tabbar">{links("tab")}</nav>
    </div>
  );
}
