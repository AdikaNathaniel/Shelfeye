"use client";

import Link from "next/link";
import { useState } from "react";
import { InventoryRow, Shelf, StockLevel, shelfName, stockLevel, timeAgo } from "@/lib/api";
import { BoxIcon, SearchIcon } from "./Icons";
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

type Props = { rows: InventoryRow[]; shelves: Shelf[]; loading: boolean };

export default function InventoryTable({ rows, shelves, loading }: Props) {
  const [query, setQuery] = useState("");
  const [shelfId, setShelfId] = useState(""); // "" means all shelves
  const [filter, setFilter] = useState<Filter>("all");

  // The shelf may have been deleted in Settings since it was picked.
  const activeShelf = shelves.find((s) => String(s.id) === shelfId) ?? null;

  const q = query.trim().toLowerCase();
  const visible = rows
    .filter((r) => !activeShelf || r.node_id === activeShelf.node_id)
    .filter((r) => matchesFilter(stockLevel(r.count), filter))
    .filter((r) => !q || r.name.toLowerCase().includes(q) || r.label_text.toLowerCase().includes(q))
    .sort((a, b) => a.count - b.count || a.name.localeCompare(b.name)); // lowest stock first

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>All products</h2>
          <p>Sorted by stock level, lowest first</p>
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
        <select className="select" aria-label="Filter by shelf" value={activeShelf ? shelfId : ""} onChange={(e) => setShelfId(e.target.value)}>
          <option value="">All shelves</option>
          {shelves.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        {!loading && !shelves.length && (
          <span className="muted small">
            <Link href="/settings" className="link">Add shelves in Settings</Link> to filter by shelf.
          </span>
        )}
      </div>

      {loading ? (
        <div className="empty">Loading stock…</div>
      ) : !rows.length ? (
        <EmptyState icon={<BoxIcon />} title="No products yet">
          Products appear here once a shelf camera sends its first count.
        </EmptyState>
      ) : activeShelf && !activeShelf.node_id ? (
        <EmptyState icon={<BoxIcon />} title={`No camera on ${activeShelf.name} yet`}>
          Assign a camera to this shelf in <Link href="/settings" className="link">Settings</Link> to see its products.
        </EmptyState>
      ) : !visible.length ? (
        <EmptyState icon={<SearchIcon />} title="Nothing matches">
          Try a different search, shelf or stock filter.
        </EmptyState>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Product</th><th>Shelf</th><th>Status</th><th className="num">Count</th><th>Last updated</th></tr>
              </thead>
              <tbody>
                {visible.map((r) => (
                  <tr key={`${r.node_id}/${r.name}`}>
                    <td className="product">
                      <div className="product-name">{r.name}</div>
                      {r.label_text && r.label_text !== r.name && <div className="product-label">Label: {r.label_text}</div>}
                    </td>
                    <td><span className="tag">{shelfName(r.node_id, shelves)}</span></td>
                    <td><StockPill level={stockLevel(r.count)} /></td>
                    <td className="num">{r.count}</td>
                    <td className="muted" title={new Date(r.updated_at).toLocaleString()}>{timeAgo(r.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-foot">Showing {visible.length} of {rows.length} products</div>
        </>
      )}
    </section>
  );
}
