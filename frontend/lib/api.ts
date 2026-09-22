// Server-side-only backend API client for fetching portfolio data.
// This module runs only in Next.js Server Components and uses process.env without NEXT_PUBLIC_ prefix
// because BACKEND_URL and DASHBOARD_API_KEY must never be exposed to client-side JavaScript.

import type { PortfolioCurrent, PortfolioMetrics, PortfolioSnapshot, WatchlistEntry } from "./types";

function backendUrl(path: string): string {
  const base = process.env.BACKEND_URL;
  if (!base) {
    throw new Error("BACKEND_URL environment variable is not set");
  }
  return `${base}${path}`;
}

function authHeaders(): HeadersInit {
  const apiKey = process.env.DASHBOARD_API_KEY;
  if (!apiKey) {
    throw new Error("DASHBOARD_API_KEY environment variable is not set");
  }
  return { Authorization: `Bearer ${apiKey}` };
}

export async function backendRequest(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(backendUrl(path), {
    ...init,
    headers: { ...authHeaders(), ...init.headers },
    cache: "no-store",
  });
}

export async function getPortfolioCurrent(): Promise<PortfolioCurrent> {
  const response = await backendRequest("/api/portfolio/current");
  if (!response.ok) {
    throw new Error(`Failed to fetch current portfolio: ${response.status}`);
  }
  return response.json();
}

export async function getPortfolioHistory(): Promise<PortfolioSnapshot[]> {
  const response = await backendRequest("/api/portfolio/history");
  if (!response.ok) {
    throw new Error(`Failed to fetch portfolio history: ${response.status}`);
  }
  return response.json();
}

export async function getPortfolioMetrics(): Promise<PortfolioMetrics> {
  const response = await backendRequest("/api/portfolio/metrics");
  if (!response.ok) {
    throw new Error(`Failed to fetch portfolio metrics: ${response.status}`);
  }
  return response.json();
}

export async function getWatchlist(): Promise<WatchlistEntry[]> {
  const response = await backendRequest("/api/watchlist");
  if (!response.ok) {
    throw new Error(`Failed to fetch watchlist: ${response.status}`);
  }
  return response.json();
}
