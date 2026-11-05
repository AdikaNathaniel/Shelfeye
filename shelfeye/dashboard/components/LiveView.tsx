"use client";

import { useEffect, useRef, useState } from "react";
import { LIVE_VIEW_MAX_MINUTES } from "@/lib/api";
import { useShelfName } from "./DataProvider";

type State = "connecting" | "watching" | "retrying" | "timed-out";

const FIRST_FRAME_TIMEOUT_MS = 20_000; // the Pi needs a few seconds to switch to video
const RETRY_DELAYS_MS = [2_000, 4_000, 8_000, 15_000]; // the last one repeats

export default function LiveView({ nodeId, onClose }: { nodeId: string; onClose: () => void }) {
  const [state, setState] = useState<State>("connecting");
  const [attempt, setAttempt] = useState(0); // each attempt opens a fresh stream
  const [failures, setFailures] = useState(0); // in a row, reset by the first frame
  const imgRef = useRef<HTMLImageElement>(null);
  const shelfName = useShelfName();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // While connecting: watch for the first frame (onLoad isn't reliable for MJPEG),
  // and give up on this attempt if none arrives in time.
  useEffect(() => {
    if (state !== "connecting") return;
    const started = Date.now();
    const poll = setInterval(() => {
      if ((imgRef.current?.naturalWidth ?? 0) > 0) {
        setFailures(0);
        setState("watching");
      } else if (Date.now() - started > FIRST_FRAME_TIMEOUT_MS) {
        setState("retrying");
      }
    }, 500);
    return () => clearInterval(poll);
  }, [state, attempt]);

  // After a failed attempt, wait a little longer each time, then try again.
  useEffect(() => {
    if (state !== "retrying") return;
    const delay = RETRY_DELAYS_MS[Math.min(failures, RETRY_DELAYS_MS.length - 1)];
    const timer = setTimeout(() => reconnect(), delay);
    return () => clearTimeout(timer);
  }, [state, failures]);

  // The Pi ends the stream after this long; stop showing a frozen frame.
  useEffect(() => {
    if (state !== "watching") return;
    const timer = setTimeout(() => setState("timed-out"), LIVE_VIEW_MAX_MINUTES * 60 * 1000);
    return () => clearTimeout(timer);
  }, [state, attempt]);

  function fail() {
    setFailures((n) => n + 1);
    setState("retrying");
  }

  function reconnect() {
    setAttempt((n) => n + 1);
    setState("connecting");
  }

  const streaming = state === "connecting" || state === "watching";

  return (
    <div className="overlay" onClick={onClose}>
      <div className="live-card" role="dialog" aria-label={`Live view of ${shelfName(nodeId)}`} onClick={(e) => e.stopPropagation()}>
        <div className="card-head">
          <h2>
            Live view · {shelfName(nodeId)}
            {state === "watching" && <span className="live-tag">LIVE</span>}
          </h2>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
        <div className="live-body">
          {streaming && (
            <>
              {/* Sits under the image and shows until the first frame covers it. */}
              <p className="live-message">
                {attempt === 0 ? "Connecting to the camera… this can take a few seconds." : "Reconnecting to the camera…"}
              </p>
              {/* Unmounting this <img> closes the stream, which lets the Pi resume counting. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                ref={imgRef}
                key={attempt}
                src={`/api/nodes/${encodeURIComponent(nodeId)}/stream?session=${attempt}`}
                alt={`Live camera feed from ${nodeId}`}
                onError={fail}
              />
            </>
          )}
          {state === "retrying" && (
            <p className="live-message">
              <span className="spinner" /> Waiting for the camera, trying again in a moment…
              {failures >= 3 && <> Make sure it&apos;s powered on and connected to the internet.</>}{" "}
              <button className="link" onClick={reconnect}>Retry now</button>
            </p>
          )}
          {state === "timed-out" && (
            <p className="live-message">
              Live view closed after {LIVE_VIEW_MAX_MINUTES} minutes so counting can continue.{" "}
              <button className="link" onClick={reconnect}>Watch again</button>
            </p>
          )}
        </div>
        <p className="muted live-note">
          Counting on this shelf pauses while live view is open and resumes when you close it.
        </p>
      </div>
    </div>
  );
}
