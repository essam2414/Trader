"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { TrendsPreferences } from "./types";

export const TREND_RANGES: TrendsPreferences["range"][] = ["1W", "1M", "3M", "1Y", "MAX"];
const PREFERENCES_PATH = "/api/watchlist/trends/preferences";
type Layout = Pick<TrendsPreferences, "assetIds" | "range">;

export function readSavedTrends(value: string | null): Layout {
  if (value) {
    try {
      const candidate = JSON.parse(value) as Partial<Layout> | null;
      if (candidate && typeof candidate === "object") {
        return {
          assetIds: Array.isArray(candidate.assetIds)
            ? [...new Set(candidate.assetIds.filter((id): id is string => typeof id === "string" && id.length > 0 && id.length <= 36))].slice(0, 50)
            : [],
          range: TREND_RANGES.includes(candidate.range as TrendsPreferences["range"]) ? candidate.range! : "1W",
        };
      }
    } catch { /* Invalid legacy data has no layout to import. */ }
  }
  return { assetIds: [], range: "1W" };
}

function layoutKey(layout: Layout): string {
  return JSON.stringify({ assetIds: layout.assetIds, range: layout.range });
}

async function writeLayout(layout: Layout, initializeOnly = false): Promise<TrendsPreferences> {
  const response = await fetch(`${PREFERENCES_PATH}${initializeOnly ? "?initializeOnly=true" : ""}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: layoutKey(layout),
    keepalive: true,
  });
  if (!response.ok) throw new Error("Trends changes could not be saved. Your changes are still shown here.");
  return response.json() as Promise<TrendsPreferences>;
}

export function useTrendsPreferences() {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [range, setRange] = useState<TrendsPreferences["range"]>("1W");
  const [hydrated, setHydrated] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savedKeyRef = useRef<string | null>(null);
  const pendingRef = useRef<Layout | null>(null);
  const savingRef = useRef(false);

  const load = useCallback(async (signal?: AbortSignal, refresh = false) => {
    const previousKey = savedKeyRef.current;
    if (refresh && (previousKey === null || savingRef.current || pendingRef.current !== null)) return;
    setLoadError(null);
    try {
      const response = await fetch(PREFERENCES_PATH, { cache: "no-store", signal });
      if (!response.ok) throw new Error("Saved Trends layout could not be loaded.");
      let preferences = await response.json() as TrendsPreferences;
      if (signal?.aborted) return;
      if (!preferences.initialized) {
        let legacy: Layout = { assetIds: [], range: "1W" };
        try {
          legacy = readSavedTrends(window.localStorage.getItem("trader.trends.v1"));
        } catch { /* Browser storage is optional and used only for the one-time import. */ }
        if (legacy.assetIds.length > 0) {
          const watchlistResponse = await fetch("/api/watchlist", { cache: "no-store", signal });
          if (!watchlistResponse.ok) throw new Error("Saved Trends layout could not be loaded.");
          const watchlist = await watchlistResponse.json() as { assetId: string }[];
          const available = new Set(watchlist.map((entry) => entry.assetId));
          legacy.assetIds = legacy.assetIds.filter((id) => available.has(id));
          if (signal?.aborted) return;
          if (legacy.assetIds.length > 0) preferences = await writeLayout(legacy, true);
        }
      }
      if (signal?.aborted) return;
      if (refresh && (savingRef.current || pendingRef.current !== null || savedKeyRef.current !== previousKey)) return;
      savedKeyRef.current = layoutKey(preferences);
      setSelectedIds(preferences.assetIds);
      setRange(preferences.range);
      setHydrated(true);
    } catch {
      if (!signal?.aborted) setLoadError("Saved Trends layout could not be loaded.");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => void load(controller.signal), 0);
    const onReturn = () => {
      if (document.visibilityState === "visible") void load(controller.signal, true);
    };
    document.addEventListener("visibilitychange", onReturn);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onReturn);
    };
  }, [load]);

  const flush = useCallback(async () => {
    if (savingRef.current || pendingRef.current === null) return;
    savingRef.current = true;
    setSaving(true);
    while (pendingRef.current !== null) {
      const next = pendingRef.current;
      pendingRef.current = null;
      try {
        await writeLayout(next);
        savedKeyRef.current = layoutKey(next);
        setSaveError(null);
      } catch {
        setSaveError("Trends changes could not be saved. Your changes are still shown here.");
        // Keep the newest layout for retry; never roll the screen back to an older response.
        pendingRef.current ??= next;
        break;
      }
    }
    savingRef.current = false;
    setSaving(false);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    const next = { assetIds: selectedIds, range };
    // A change back to the saved layout still needs writing if another write is in flight.
    if (!savingRef.current && pendingRef.current === null && layoutKey(next) === savedKeyRef.current) return;
    pendingRef.current = next;
    void flush();
  }, [hydrated, selectedIds, range, flush]);

  return {
    selectedIds, setSelectedIds, range, setRange, hydrated, loadError, saveError, saving,
    retryLoad: () => void load(), retrySave: () => void flush(),
  };
}
