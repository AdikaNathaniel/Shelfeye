"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { login } from "@/lib/api";
import { FormError, MobileBrand, PasswordInput, nextPath } from "@/components/AuthFields";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      router.replace(nextPath());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <MobileBrand />
      <h1>Welcome back</h1>
      <p>Log in to see your shelves.</p>

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
      <div className="field">
        <label htmlFor="password">Password</label>
        <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="current-password" placeholder="Your password" />
      </div>

      <button className="btn btn-primary btn-block" type="submit" disabled={busy || !email || !password}>
        {busy ? <span className="spinner" /> : "Log in"}
      </button>

      <div className="switch-auth">
        New to ShelfEye? <Link href="/register">Create an account</Link>
      </div>
    </form>
  );
}
