"use client";

import { useState } from "react";
import { AlertIcon, EyeIcon, EyeOffIcon, Logo } from "./Icons";

export function MobileBrand() {
  return (
    <div className="brand mobile-brand">
      <Logo />
      <div>
        <div className="brand-name">ShelfEye</div>
        <div className="brand-sub">Smart shelf counting</div>
      </div>
    </div>
  );
}

export function FormError({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div className="form-error" role="alert">
      <AlertIcon size={16} />
      <span>{message}</span>
    </div>
  );
}

export function PasswordInput({
  id, value, onChange, autoComplete, placeholder,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  placeholder?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="password">
      <input
        id={id}
        className="input"
        type={visible ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        placeholder={placeholder}
        required
      />
      <button
        type="button"
        className="icon-btn"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
      >
        {visible ? <EyeOffIcon size={17} /> : <EyeIcon size={17} />}
      </button>
    </div>
  );
}

/** Where to go after logging in: the page the user was sent away from, if it's one of ours. */
export function nextPath() {
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}
