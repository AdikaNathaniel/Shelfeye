"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { resetPassword } from "@/lib/api";
import { FormError, MobileBrand, PasswordInput } from "@/components/AuthFields";

const MIN_PASSWORD_LENGTH = 8; // matches the server

function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!token) {
    return (
      <div className="auth-form">
        <MobileBrand />
        <h1>This link is incomplete</h1>
        <p>Open the link from your reset email again, or request a new one.</p>
        <Link className="btn btn-primary btn-block" href="/forgot-password">Request a new link</Link>
      </div>
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < MIN_PASSWORD_LENGTH) return setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
    if (password !== confirm) return setError("The two passwords don't match.");
    setBusy(true);
    try {
      await resetPassword(token, password); // also logs this browser in
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  const expired = error.includes("expired");

  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <MobileBrand />
      <h1>Choose a new password</h1>
      <p>You&apos;ll be logged in with it straight away, and logged out on your other devices.</p>

      <FormError message={error} />
      {expired && (
        <p className="switch-auth" style={{ marginTop: -6, marginBottom: 16 }}>
          <Link href="/forgot-password">Request a new link</Link>
        </p>
      )}

      <div className="field">
        <label htmlFor="password">New password</label>
        <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="new-password" placeholder="At least 8 characters" />
      </div>
      <div className="field">
        <label htmlFor="confirm">Repeat new password</label>
        <PasswordInput id="confirm" value={confirm} onChange={setConfirm} autoComplete="new-password" placeholder="Type it again" />
      </div>

      <button className="btn btn-primary btn-block" type="submit" disabled={busy || !password || !confirm}>
        {busy ? <span className="spinner" /> : "Save new password"}
      </button>

      <div className="switch-auth">
        <Link href="/login">Back to log in</Link>
      </div>
    </form>
  );
}

export default function ResetPasswordPage() {
  // useSearchParams needs a Suspense boundary so the page can be prerendered.
  return (
    <Suspense fallback={<div className="auth-form muted">Loading…</div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
