"use client";

import { useState } from "react";
import { LOW_STOCK, isReporting, timeAgo } from "@/lib/api";
import { useShelfEye, useShelfName } from "@/components/DataProvider";
import { CameraIcon, VideoIcon } from "@/components/Icons";
import LiveView from "@/components/LiveView";
import { EmptyState } from "@/components/ui";

export default function CamerasPage() {
  const { data } = useShelfEye();
  const [liveNode, setLiveNode] = useState<string | null>(null);
  const shelfName = useShelfName();

  if (!data) return <div className="card empty">Loading cameras…</div>;
  if (!data.nodes.length) {
    return (
      <div className="card">
        <EmptyState icon={<CameraIcon />} title="No cameras yet">
          Set up a ShelfEye camera with the setup guide. It appears here after its first check-in, usually within 5 minutes of starting.
        </EmptyState>
      </div>
    );
  }

  return (
    <>
      <div className="camera-grid">
        {data.nodes.map((n) => {
          const products = data.inventory.filter((r) => r.node_id === n.node_id);
          const low = products.filter((r) => r.count <= LOW_STOCK).length;
          const ok = isReporting(n);
          return (
            <div key={n.node_id} className="card camera-card">
              <div className="camera-top">
                <div className="camera-icon"><CameraIcon size={20} /></div>
                <div className="row-main">
                  <div className="camera-name">{shelfName(n.node_id)}</div>
                  {shelfName(n.node_id) !== n.node_id && <div className="row-sub">Camera {n.node_id}</div>}
                  <div className="camera-status">
                    <span className={`dot ${ok ? "" : "stale"}`} />
                    {ok ? "Reporting" : "Not heard from recently"} · {timeAgo(n.last_seen)}
                  </div>
                </div>
              </div>
              <div className="camera-stats">
                <div className="camera-stat"><div>Products</div><div>{products.length}</div></div>
                <div className="camera-stat"><div>Need restocking</div><div style={{ color: low ? "var(--out)" : undefined }}>{low}</div></div>
              </div>
              {n.live_view ? (
                <button className="btn btn-primary" onClick={() => setLiveNode(n.node_id)}>
                  <VideoIcon size={16} /> Open live view
                </button>
              ) : (
                <button className="btn" disabled title="Live view is turned off on this camera, or it runs older ShelfEye software">
                  Live view unavailable
                </button>
              )}
              {n.local_view_url && (
                <div className="camera-local">
                  {/* A new tab: this page is https and the camera is plain http on the
                      local network, so browsers won't show its video inside this page. */}
                  <a className="btn" href={n.local_view_url} target="_blank" rel="noopener noreferrer">
                    <VideoIcon size={16} /> Fast local view (same Wi-Fi) ↗
                  </a>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="muted small" style={{ marginTop: 14 }}>
        Counting on a shelf pauses while its live view is open, and live view closes itself after 10 minutes.
      </p>
      {liveNode && <LiveView key={liveNode} nodeId={liveNode} onClose={() => setLiveNode(null)} />}
    </>
  );
}
