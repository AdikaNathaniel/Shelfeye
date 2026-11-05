"use client";

import Link from "next/link";
import { useState } from "react";
import { forgotPassword } from "@/lib/api";
import { FormError, MobileBrand } from "@/components/AuthFields";
import { CheckIcon } from "@/components/Icons";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await forgotPassword(email.trim());
      setSentTo(email.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (sentTo) {
    return (
      <div className="auth-form">
        <MobileBrand />
        <h1>Check your email</h1>
        <p>We&apos;ve sent the reset link if there&apos;s an account for this address.</p>
        <div className="form-success" role="status">
          <CheckIcon size={16} />
          <span>
            If <strong>{sentTo}</strong> has a ShelfEye account, a link to choose a new password is on its way.
            It works for 60 minutes. Check your spam folder if it isn&apos;t there in a few minutes.
          </span>
        </div>
        <button className="btn btn-block" onClick={() => setSentTo("")}>Use a different email</button>
        <div className="switch-auth">
          Remembered it? <Link href="/login">Back to log in</Link>
        </div>
      </div>
    );
  }

  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <MobileBrand />
      <h1>Forgot your password?</h1>
      <p>Enter the email you signed up with and we&apos;ll send you a link to choose a new one.</p>

      <FormError message={error} />

      <div className="field">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          className="input"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          placeholder="you@example.com"
          required
          autoFocus
        />
      </div>

      <button className="btn btn-primary btn-block" type="submit" disabled={busy || !email.trim()}>
        {busy ? <span className="spinner" /> : "Send reset link"}
      </button>

      <div className="switch-auth">
        Remembered it? <Link href="/login">Back to log in</Link>
      </div>
    </form>
  );
}
