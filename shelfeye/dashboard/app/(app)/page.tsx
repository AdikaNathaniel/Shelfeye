"use client";

import Link from "next/link";
import { useState } from "react";
import { LOW_STOCK, isReporting, isToday, stockLevel, timeAgo } from "@/lib/api";
import { useShelfEye } from "@/components/DataProvider";
import { AlertIcon, ArrowDownIcon, BoxIcon, CameraIcon, CheckIcon, ChevronRightIcon, ActivityIcon, VideoIcon } from "@/components/Icons";
import LiveView from "@/components/LiveView";
import { EmptyState, EventList, StatCard, StockPill } from "@/components/ui";

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export default function OverviewPage() {
  const { user, data } = useShelfEye();
  const [liveNode, setLiveNode] = useState<string | null>(null);
  const firstName = user.name.split(/\s+/)[0];

  const inventory = data?.inventory ?? [];
  const events = data?.events ?? [];
  const nodes = data?.nodes ?? [];
  const attention = inventory.filter((r) => r.count <= LOW_STOCK).sort((a, b) => a.count - b.count);
  const out = attention.filter((r) => r.count === 0).length;
  const today = events.filter((e) => isToday(e.captured_at));
  const taken = today.filter((e) => e.delta < 0).reduce((sum, e) => sum - e.delta, 0);
  const added = today.filter((e) => e.delta > 0).reduce((sum, e) => sum + e.delta, 0);
  const units = inventory.reduce((sum, r) => sum + r.count, 0);
  const reporting = nodes.filter(isReporting).length;
  const dash = data ? null : "–";

  return (
    <>
      <div className="welcome">
        <h2>{greeting()}, {firstName}</h2>
        <p className="muted small">
          {new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
        </p>
      </div>

      <section className="stats">
        <StatCard label="Products tracked" value={dash ?? inventory.length} hint={`${units} units on shelves`} icon={<BoxIcon />} />
        <StatCard label="Need restocking" value={dash ?? attention.length} hint={`${out} out of stock`} icon={<AlertIcon />} tone="danger" />
        <StatCard label="Taken today" value={dash ?? taken} hint={`${added} added today`} icon={<ArrowDownIcon />} />
        <StatCard label="Cameras online" value={dash ?? `${reporting}/${nodes.length}`} hint={reporting === nodes.length ? "All reporting normally" : "Some not reporting"} icon={<CameraIcon />} tone="good" />
      </section>

      <div className="grid-2">
        <section className="card">
          <div className="card-head">
            <div>
              <h2>Needs attention</h2>
              <p>Products at {LOW_STOCK} or fewer units</p>
            </div>
            <Link href="/inventory" className="link">Inventory <ChevronRightIcon size={15} /></Link>
          </div>
          <div className="card-body">
            {data && !inventory.length && (
              <EmptyState icon={<BoxIcon />} title="No stock data yet">
                Products appear here once a shelf camera sends its first count.
              </EmptyState>
            )}
            {data && inventory.length > 0 && !attention.length && (
              <div className="all-good"><CheckIcon /> Every product is well stocked.</div>
            )}
            <ul className="rows">
              {attention.slice(0, 6).map((r) => (
                <li key={`${r.node_id}/${r.name}`} className="row">
                  <div className="row-main">
                    <div className="row-title">{r.name}</div>
                    <div className="row-sub">{r.node_id} · updated {timeAgo(r.updated_at)}</div>
                  </div>
                  <StockPill level={stockLevel(r.count)} />
                  <div className="row-end big-count">{r.count}</div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <div>
              <h2>Recent activity</h2>
              <p>Latest changes the cameras saw</p>
            </div>
            <Link href="/activity" className="link">View all <ChevronRightIcon size={15} /></Link>
          </div>
          <div className="card-body">
            {data && !events.length && (
              <EmptyState icon={<ActivityIcon />} title="No activity yet">
                When an item is taken or added, it shows up here.
              </EmptyState>
            )}
            <EventList events={events.slice(0, 6)} />
          </div>
        </section>
      </div>

      <section className="card">
        <div className="card-head">
          <div>
            <h2>Shelf cameras</h2>
            <p>{nodes.length ? `${reporting} of ${nodes.length} reporting` : "No cameras connected yet"}</p>
          </div>
          <Link href="/cameras" className="link">Manage <ChevronRightIcon size={15} /></Link>
        </div>
        <div className="card-body">
          {data && !nodes.length && (
            <EmptyState icon={<CameraIcon />} title="No cameras yet">
              Set up a ShelfEye camera with the setup guide. It appears here after its first check-in.
            </EmptyState>
          )}
          <div className="camera-strip">
            {nodes.map((n) => (
              <div key={n.node_id} className="camera-mini">
                <span className={`dot ${isReporting(n) ? "" : "stale"}`} />
                <div className="row-main">
                  <div className="row-title">{n.node_id}</div>
                  <div className="row-sub">Last seen {timeAgo(n.last_seen)}</div>
                </div>
                {n.live_view_url && (
                  <button className="btn btn-soft" onClick={() => setLiveNode(n.node_id)}>
                    <VideoIcon size={16} /> Live
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {liveNode && <LiveView key={liveNode} nodeId={liveNode} onClose={() => setLiveNode(null)} />}
    </>
  );
}
