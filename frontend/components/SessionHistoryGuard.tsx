"use client";

import { useEffect } from "react";

export function SessionHistoryGuard() {
  useEffect(() => {
    const verifySession = async () => {
      try {
        const response = await fetch("/api/auth/session", { cache: "no-store" });
        if (!response.ok) {
          window.location.replace("/login");
        }
      } catch {
        window.location.replace("/login");
      }
    };
    const revalidateSession = () => {
      void verifySession();
    };
    const revalidateWhenVisible = () => {
      if (document.visibilityState === "visible") {
        revalidateSession();
      }
    };
    const preventBackForwardCache = () => {
      // Browsers must discard this protected page instead of restoring its stale UI.
    };

    window.addEventListener("pageshow", revalidateSession);
    window.addEventListener("popstate", revalidateSession);
    window.addEventListener("unload", preventBackForwardCache);
    document.addEventListener("visibilitychange", revalidateWhenVisible);
    return () => {
      window.removeEventListener("pageshow", revalidateSession);
      window.removeEventListener("popstate", revalidateSession);
      window.removeEventListener("unload", preventBackForwardCache);
      document.removeEventListener("visibilitychange", revalidateWhenVisible);
    };
  }, []);

  return null;
}
