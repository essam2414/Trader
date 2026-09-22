"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const REFRESH_INTERVAL_MS = 5_000;

export function PageAutoRefresh({ intervalMs }: { intervalMs: number }) {
  const { refresh } = useRouter();

  useEffect(() => {
    let interval: number | undefined;

    const stopRefresh = () => {
      if (interval !== undefined) {
        window.clearInterval(interval);
        interval = undefined;
      }
    };

    const startRefresh = () => {
      if (document.visibilityState === "visible" && interval === undefined) {
        interval = window.setInterval(refresh, intervalMs);
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        startRefresh();
      } else {
        stopRefresh();
      }
    };

    startRefresh();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      stopRefresh();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [intervalMs, refresh]);

  return null;
}

export function PortfolioAutoRefresh() {
  return <PageAutoRefresh intervalMs={REFRESH_INTERVAL_MS} />;
}
