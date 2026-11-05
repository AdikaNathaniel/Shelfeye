"use client";

import Link from "next/link";
import { useState } from "react";
import { InventoryRow, LOW_STOCK, Shelf, StockLevel, stockLevel, timeAgo } from "@/lib/api";
import { BoxIcon, CameraIcon, SearchIcon } from "./Icons";
import { EmptyState, StockPill } from "./ui";

type Filter = "all" | "low" | "out";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "low", label: "Low" },
  { value: "out", label: "Out of stock" },
];

function matchesFilter(level: StockLevel, filter: Filter) {
  if (filter === "all") return true;
  if (filter === "out") return level === "out";
  return level !== "ok"; // "Low" includes out-of-stock items, which are the lowest of all
}

/** One section on the page: a shelf from Settings, or a camera that isn't on any shelf yet. */
type Group = { key: string; name: string; nodeId: string | null; onShelf: boolean; rows: InventoryRow[] };

function groupRows(rows: InventoryRow[], shelves: Shelf[]): Group[] {
  const groups: Group[] = shelves.map((s) => ({
    key: `shelf-${s.id}`,
    name: s.name,
    nodeId: s.node_id,
    onShelf: true,
    rows: rows.filter((r) => r.node_id === s.node_id),
  }));
  const assigned = new Set(shelves.map((s) => s.node_id));
  const loose = [...new Set(rows.map((r) => r.node_id))].filter((id) => !assigned.has(id)).sort();
  for (const nodeId of loose) {
    groups.push({ key: `camera-${nodeId}`, name: nodeId, nodeId, onShelf: false, rows: rows.filter((r) => r.node_id === nodeId) });
  }
  return groups;
}

function ShelfSection({ group, visible }: { group: Group; visible: InventoryRow[] }) {
  const low = group.rows.filter((r) => r.count <= LOW_STOCK).length;
  const summary = group.rows.length
    ? `${group.rows.length} product${group.rows.length === 1 ? "" : "s"}${low ? ` · ${low} need restocking` : ""}`
    : "No products yet";

  return (
    <section className="card shelf-section">
      <div className="card-head">
        <div>
          <h2>{group.name}</h2>
          <p>{summary}</p>
        </div>
        {group.nodeId && (
          <span className="tag">
            <CameraIcon size={13} /> {group.onShelf ? `Camera ${group.nodeId}` : "Not on a shelf yet"}
          </span>
        )}
      </div>

      {!group.nodeId ? (
        <EmptyState icon={<CameraIcon />} title="No camera on this shelf yet">
          Assign a camera to {group.name} in <Link href="/settings" className="link">Settings</Link> and its products will appear here.
        </EmptyState>
      ) : !group.rows.length ? (
        <EmptyState icon={<BoxIcon />} title="Waiting for the first count">
          Products appear here as soon as camera {group.nodeId} sends its first count.
        </EmptyState>
      ) : !visible.length ? (
        <div className="empty small">No products on this shelf match your search or filter.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Product</th><th>Status</th><th className="num">Count</th><th>Last updated</th></tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={`${r.node_id}/${r.name}`}>
                  <td className="product">
                    <div className="product-name">{r.name}</div>
                    {r.label_text && r.label_text !== r.name && <div className="product-label">Label: {r.label_text}</div>}
                  </td>
                  <td><StockPill level={stockLevel(r.count)} /></td>
                  <td className="num">{r.count}</td>
                  <td className="muted" title={new Date(r.updated_at).toLocaleString()}>{timeAgo(r.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

type Props = { rows: InventoryRow[]; shelves: Shelf[]; loading: boolean };

export default function InventoryTable({ rows, shelves, loading }: Props) {
  const [query, setQuery] = useState("");
  const [shelfKey, setShelfKey] = useState(""); // "" means all shelves
  const [filter, setFilter] = useState<Filter>("all");

  const groups = groupRows(rows, shelves);
  // The shelf may have been deleted in Settings since it was picked.
  const activeKey = groups.some((g) => g.key === shelfKey) ? shelfKey : "";
  const shown = groups.filter((g) => !activeKey || g.key === activeKey);

  const q = query.trim().toLowerCase();
  const visibleRows = (group: Group) =>
    group.rows
      .filter((r) => matchesFilter(stockLevel(r.count), filter))
      .filter((r) => !q || r.name.toLowerCase().includes(q) || r.label_text.toLowerCase().includes(q))
      .sort((a, b) => a.count - b.count || a.name.localeCompare(b.name)); // lowest stock first

  return (
    <div className="inventory">
      <section className="card">
        <div className="card-head">
          <div>
            <h2>All products</h2>
            <p>Grouped by shelf, lowest stock first</p>
          </div>
          <div className="segmented" role="group" aria-label="Filter by stock level">
            {FILTERS.map((f) => (
              <button key={f.value} aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}>
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <div className="toolbar">
          <div className="input-icon">
            <SearchIcon size={16} />
            <input
              className="input"
              type="search"
              placeholder="Search products or label text…"
              aria-label="Search products"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <select className="select" aria-label="Filter by shelf" value={activeKey} onChange={(e) => setShelfKey(e.target.value)}>
            <option value="">All shelves</option>
            {groups.map((g) => <option key={g.key} value={g.key}>{g.name}</option>)}
          </select>
        </div>
      </section>

      {loading ? (
        <div className="card empty">Loading stock…</div>
      ) : !groups.length ? (
        <div className="card">
          <EmptyState icon={<BoxIcon />} title="No products yet">
            Products appear here once a shelf camera sends its first count.
          </EmptyState>
        </div>
      ) : (
        shown.map((g) => <ShelfSection key={g.key} group={g} visible={visibleRows(g)} />)
      )}
    </div>
  );
}
