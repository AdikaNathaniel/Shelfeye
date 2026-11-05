// Small presentational pieces shared by the pages.
import { STOCK_LABEL, StockEvent, StockLevel, clockTime, dayLabel, timeAgo } from "@/lib/api";
import { ArrowDownIcon, ArrowUpIcon } from "./Icons";

export function StatCard({
  label, value, hint, icon, tone = "accent",
}: {
  label: string;
  value: number | string;
  hint: string;
  icon: React.ReactNode;
  tone?: "accent" | "danger" | "good";
}) {
  return (
    <div className="card stat">
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        <span className={`stat-icon ${tone === "accent" ? "" : tone}`}>{icon}</span>
      </div>
      <div className={`stat-value ${tone === "danger" && value !== 0 ? "danger" : ""}`}>{value}</div>
      <div className="stat-hint">{hint}</div>
    </div>
  );
}

export function StockPill({ level }: { level: StockLevel }) {
  return <span className={`pill ${level}`}>{STOCK_LABEL[level]}</span>;
}

export function EmptyState({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

function EventRow({ event, showDayTime }: { event: StockEvent; showDayTime: boolean }) {
  const taken = event.delta < 0;
  return (
    <li className="row">
      <span className={`delta ${taken ? "taken" : "added"}`}>{taken ? <ArrowDownIcon /> : <ArrowUpIcon />}</span>
      <div className="row-main">
        <div className="row-title">{event.name}</div>
        <div className="row-sub">
          {taken ? "Taken" : "Added"} · {event.previous} → {event.current} · {event.node_id}
        </div>
      </div>
      <div className="row-end">
        <div className={`delta-num ${taken ? "taken" : "added"}`}>{taken ? `−${-event.delta}` : `+${event.delta}`}</div>
        <div className="row-sub" title={new Date(event.captured_at).toLocaleString()}>
          {showDayTime ? clockTime(event.captured_at) : timeAgo(event.captured_at)}
        </div>
      </div>
    </li>
  );
}

/** A list of stock changes, optionally split under "Today", "Yesterday", … headings. */
export function EventList({ events, groupByDay = false }: { events: StockEvent[]; groupByDay?: boolean }) {
  if (!groupByDay) {
    return <ul className="rows">{events.map((e) => <EventRow key={e.id} event={e} showDayTime={false} />)}</ul>;
  }
  const groups: { label: string; events: StockEvent[] }[] = [];
  for (const event of events) {
    const label = dayLabel(event.captured_at);
    if (groups.at(-1)?.label !== label) groups.push({ label, events: [] });
    groups.at(-1)!.events.push(event);
  }
  return (
    <div>
      {groups.map((group) => (
        <section key={group.label}>
          <div className="day">{group.label}</div>
          <ul className="rows">{group.events.map((e) => <EventRow key={e.id} event={e} showDayTime />)}</ul>
        </section>
      ))}
    </div>
  );
}
