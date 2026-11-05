"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { register } from "@/lib/api";
import { FormError, MobileBrand, PasswordInput } from "@/components/AuthFields";

const MIN_PASSWORD_LENGTH = 8; // matches the server

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < MIN_PASSWORD_LENGTH) return setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
    if (password !== confirm) return setError("The two passwords don't match.");
    setBusy(true);
    try {
      await register(name, email, password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <MobileBrand />
      <h1>Create your account</h1>
      <p>Start tracking your shelves in minutes.</p>

      <FormError message={error} />

      <div className="field">
        <label htmlFor="name">Full name</label>
        <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="Ama Mensah" required autoFocus />
      </div>
      <div className="field">
        <label htmlFor="email">Email</label>
        <input id="email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="you@example.com" required />
      </div>
      <div className="field">
        <label htmlFor="password">Password</label>
        <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="new-password" placeholder="At least 8 characters" />
      </div>
      <div className="field">
        <label htmlFor="confirm">Confirm password</label>
        <PasswordInput id="confirm" value={confirm} onChange={setConfirm} autoComplete="new-password" placeholder="Type it again" />
      </div>

      <button className="btn btn-primary btn-block" type="submit" disabled={busy || !name || !email || !password || !confirm}>
        {busy ? <span className="spinner" /> : "Create account"}
      </button>

      <div className="switch-auth">
        Already have an account? <Link href="/login">Log in</Link>
      </div>
    </form>
  );
}
