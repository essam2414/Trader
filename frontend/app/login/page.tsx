"use client";

import { type FormEvent, useEffect, useState } from "react";

export default function LoginPage() {
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const redirectIfAuthenticated = async () => {
      try {
        const response = await fetch("/api/auth/session", { cache: "no-store" });
        if (response.ok) {
          window.location.replace("/dashboard");
        }
      } catch {
        // Leave Login available when the session check cannot be reached.
      }
    };
    const revalidateSession = () => {
      void redirectIfAuthenticated();
    };

    revalidateSession();
    window.addEventListener("pageshow", revalidateSession);
    return () => window.removeEventListener("pageshow", revalidateSession);
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });

      if (!response.ok) {
        const payload: unknown = await response.json().catch(() => null);
        const message = typeof payload === "object" && payload !== null && "message" in payload
          ? payload.message
          : "Could not sign in.";
        setError(typeof message === "string" ? message : "Could not sign in.");
        return;
      }

      // Replace Login in history so authenticated users cannot return here with Back.
      window.location.replace("/dashboard");
    } catch {
      setError("Could not sign in. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-950 p-8">
      <section className="w-full max-w-sm rounded-2xl border border-neutral-800 bg-neutral-900 p-8 shadow-2xl shadow-black/30">
        <h1 className="text-3xl font-bold tracking-tight text-neutral-100">Trader</h1>
        <p className="mt-8 text-sm text-neutral-400">Enter your four-digit PIN to access your account.</p>

        <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-sm font-medium text-neutral-300" htmlFor="pin">
              PIN
            </label>
            <input
              id="pin"
              name="pin"
              type="password"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]*"
              maxLength={4}
              value={pin}
              onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))}
              className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-4 py-3 font-mono text-lg tracking-[0.35em] text-neutral-100 outline-none transition-colors placeholder:tracking-normal focus:border-neutral-400"
              placeholder="••••"
              aria-describedby={error ? "pin-error" : undefined}
              required
              autoFocus
            />
          </div>
          {error && <p id="pin-error" className="text-sm text-rose-400">{error}</p>}
          <button
            type="submit"
            disabled={isSubmitting || pin.length !== 4}
            className="w-full rounded-lg bg-neutral-200 px-4 py-3 text-sm font-semibold text-neutral-950 transition-colors hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
