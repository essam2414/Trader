"use client";

import { useState } from "react";

export function LogoutButton() {
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogout() {
    setIsLoggingOut(true);
    setError(null);

    try {
      const response = await fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok) {
        throw new Error("Could not log out.");
      }
      // A document navigation guarantees the cleared HTTP-only cookie is observed.
      window.location.replace("/login");
    } catch (logoutError) {
      setError(logoutError instanceof Error ? logoutError.message : "Could not log out.");
      setIsLoggingOut(false);
    }
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={handleLogout}
        disabled={isLoggingOut}
        className="rounded-lg border border-neutral-700 px-4 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-500 hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isLoggingOut ? "Logging out…" : "Log out"}
      </button>
      {error && <p className="text-sm text-rose-400">{error}</p>}
    </div>
  );
}
