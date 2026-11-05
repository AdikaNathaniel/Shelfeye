"use client";

import { useState } from "react";
import { useShelfEye } from "@/components/DataProvider";
import { ActivityIcon } from "@/components/Icons";
import { EmptyState, EventList } from "@/components/ui";

type Filter = "all" | "taken" | "added";

export default function ActivityPage() {
  const { data } = useShelfEye();
  const [filter, setFilter] = useState<Filter>("all");
  const [shelf, setShelf] = useState("");

  const events = data?.events ?? [];
  const shelves = [...new Set(events.map((e) => e.node_id))].sort();
  const activeShelf = shelves.includes(shelf) ? shelf : "";
  const visible = events
    .filter((e) => filter === "all" || (filter === "taken" ? e.delta < 0 : e.delta > 0))
    .filter((e) => !activeShelf || e.node_id === activeShelf);

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Stock changes</h2>
          <p>Newest first</p>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <select className="select" aria-label="Filter by shelf" value={activeShelf} onChange={(e) => setShelf(e.target.value)}>
            <option value="">All shelves</option>
            {shelves.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <div className="segmented" role="group" aria-label="Filter by change">
            {(["all", "taken", "added"] as Filter[]).map((f) => (
              <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {f === "all" ? "All" : f === "taken" ? "Taken" : "Added"}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="card-body">
        {!data ? (
          <div className="empty">Loading activity…</div>
        ) : !visible.length ? (
          <EmptyState icon={<ActivityIcon />} title={events.length ? "Nothing matches" : "No activity yet"}>
            {events.length ? "Try a different filter." : "When an item is taken or added, it shows up here."}
          </EmptyState>
        ) : (
          <EventList events={visible} groupByDay />
        )}
      </div>
    </section>
  );
}
