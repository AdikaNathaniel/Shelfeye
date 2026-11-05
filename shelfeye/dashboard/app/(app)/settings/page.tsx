"use client";

import { useEffect, useState } from "react";
import {
  MAX_KEEP_IMAGES_DAYS, Shelf, UnauthorizedError, createShelf, deleteShelf, fetchSettings, knownCameras,
  updateSettings, updateShelf,
} from "@/lib/api";
import { useShelfEye } from "@/components/DataProvider";
import { FormError } from "@/components/AuthFields";
import { BoxIcon, LogOutIcon, PlusIcon, TrashIcon } from "@/components/Icons";
import { EmptyState } from "@/components/ui";

/** "Shelf N" with the lowest N that isn't taken yet. */
function nextShelfName(shelves: Shelf[]) {
  const taken = new Set(shelves.map((s) => s.name.toLowerCase()));
  let n = shelves.length + 1;
  while (taken.has(`shelf ${n}`)) n++;
  return `Shelf ${n}`;
}

function CameraSelect({ value, cameras, onChange, disabled, label }: {
  value: string | null;
  cameras: string[];
  onChange: (nodeId: string | null) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <select className="select" aria-label={label} value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">No camera yet</option>
      {cameras.map((c) => <option key={c} value={c}>Camera {c}</option>)}
    </select>
  );
}

function ShelfRow({ shelf, number, cameras, onError }: {
  shelf: Shelf;
  number: number;
  cameras: string[];
  onError: (message: string) => void;
}) {
  const { refresh } = useShelfEye();
  const [name, setName] = useState(shelf.name);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    onError("");
    try {
      await action();
      await refresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setName(shelf.name);
    } finally {
      setBusy(false);
    }
  }

  function saveName() {
    const trimmed = name.trim();
    if (!trimmed) return setName(shelf.name);
    if (trimmed !== shelf.name) run(() => updateShelf(shelf.id, { name: trimmed }));
  }

  return (
    <li className="row shelf-row">
      <span className="shelf-number">{number}</span>
      <input
        className="input shelf-name"
        aria-label={`Name of shelf ${number}`}
        value={name}
        maxLength={60}
        disabled={busy}
        onChange={(e) => setName(e.target.value)}
        onBlur={saveName}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") setName(shelf.name);
        }}
      />
      <CameraSelect
        label={`Camera for ${shelf.name}`}
        value={shelf.node_id}
        cameras={cameras}
        disabled={busy}
        onChange={(nodeId) => run(() => updateShelf(shelf.id, { node_id: nodeId }))}
      />
      {confirming ? (
        <div className="shelf-confirm">
          <span className="small muted">Delete?</span>
          <button className="btn btn-danger" disabled={busy} onClick={() => run(() => deleteShelf(shelf.id))}>Delete</button>
          <button className="btn btn-ghost" disabled={busy} onClick={() => setConfirming(false)}>Cancel</button>
        </div>
      ) : (
        <button className="icon-btn" title={`Delete ${shelf.name}`} aria-label={`Delete ${shelf.name}`} disabled={busy} onClick={() => setConfirming(true)}>
          <TrashIcon size={17} />
        </button>
      )}
    </li>
  );
}

function ShelvesCard() {
  const { data, refresh } = useShelfEye();
  const [name, setName] = useState("");
  const [camera, setCamera] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!data) return <section className="card empty">Loading shelves…</section>;

  const shelves = data.shelves;
  const cameras = knownCameras(data);
  const assigned = new Set(shelves.map((s) => s.node_id).filter(Boolean));
  const freeCameras = cameras.filter((c) => !assigned.has(c));
  const placeholder = nextShelfName(shelves);

  async function addShelf(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await createShelf(name.trim() || placeholder, camera);
      await refresh();
      setName("");
      setCamera(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Shelves</h2>
          <p>Add a shelf for each section a camera watches. These are the shelves you can filter by on Inventory and Activity.</p>
        </div>
      </div>
      <div className="card-body">
        <FormError message={error} />

        <form className="shelf-add" onSubmit={addShelf}>
          <input
            className="input"
            aria-label="New shelf name"
            placeholder={placeholder}
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
          />
          <CameraSelect label="Camera for the new shelf" value={camera} cameras={freeCameras} onChange={setCamera} />
          <button className="btn btn-primary" type="submit" disabled={busy}>
            <PlusIcon size={16} /> Add shelf
          </button>
        </form>

        {!shelves.length ? (
          <EmptyState icon={<BoxIcon />} title="No shelves yet">
            Add your first shelf above. Until then, Inventory shows every camera&apos;s products together.
          </EmptyState>
        ) : (
          <ul className="rows">
            {shelves.map((s, i) => (
              <ShelfRow
                key={`${s.id}:${s.name}`} // remount after a rename so the input shows the saved name
                shelf={s}
                number={i + 1}
                cameras={cameras.filter((c) => c === s.node_id || !assigned.has(c))}
                onError={setError}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function PhotoStorageCard() {
  const [saved, setSaved] = useState<number | null>(null);
  const [days, setDays] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchSettings()
      .then((s) => {
        setSaved(s.keep_images_days);
        setDays(String(s.keep_images_days));
      })
      // An expired session is handled by DataProvider's own polling.
      .catch(() => setError("Couldn't load the photo storage setting. Please refresh the page."));
  }, []);

  const value = Number(days);
  const valid = Number.isInteger(value) && value >= 1 && value <= MAX_KEEP_IMAGES_DAYS;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!valid) return setError(`Enter a number of days from 1 to ${MAX_KEEP_IMAGES_DAYS}.`);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const s = await updateSettings({ keep_images_days: value });
      setSaved(s.keep_images_days);
      setDays(String(s.keep_images_days));
      setNotice("Saved. Cameras apply it within 5 minutes.");
    } catch (err) {
      setError(
        err instanceof UnauthorizedError
          ? "Your session has expired. Please log in again."
          : err instanceof Error ? err.message : "Something went wrong. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Photo storage</h2>
          <p>How long each camera keeps its shelf photos on its SD card. Older photos are deleted.</p>
        </div>
      </div>
      <div className="card-body">
        <FormError message={error} />
        <form className="retention" onSubmit={save}>
          <label className="retention-field">
            <span className="small muted">Keep photos for</span>
            <input
              className="input"
              type="number"
              inputMode="numeric"
              min={1}
              max={MAX_KEEP_IMAGES_DAYS}
              step={1}
              aria-label="Days to keep photos"
              value={days}
              disabled={saved === null || busy}
              onChange={(e) => {
                setDays(e.target.value);
                setNotice("");
              }}
            />
            <span className="small muted">days</span>
          </label>
          <button className="btn btn-primary" type="submit" disabled={saved === null || busy || value === saved}>
            Save
          </button>
        </form>
        {notice && <p className="small muted retention-note">{notice}</p>}
      </div>
    </section>
  );
}

function AccountCard() {
  const { user, signOut } = useShelfEye();
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Account</h2>
          <p>You&apos;re signed in as</p>
        </div>
        <button className="btn" onClick={signOut}><LogOutIcon size={16} /> Log out</button>
      </div>
      <div className="card-body">
        <dl className="account">
          <div><dt>Name</dt><dd>{user.name}</dd></div>
          <div><dt>Email</dt><dd>{user.email}</dd></div>
        </dl>
      </div>
    </section>
  );
}

export default function SettingsPage() {
  return (
    <div className="settings">
      <ShelvesCard />
      <PhotoStorageCard />
      <AccountCard />
    </div>
  );
}
