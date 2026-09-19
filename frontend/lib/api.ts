// Server-side-only backend API client for fetching portfolio data.
// This module runs only in Next.js Server Components and uses process.env without NEXT_PUBLIC_ prefix
// because BACKEND_URL and DASHBOARD_API_KEY must never be exposed to client-side JavaScript.

import type { PortfolioCurrent, PortfolioSnapshot } from "./types";

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

export async function getPortfolioCurrent(): Promise<PortfolioCurrent> {
  const response = await fetch(backendUrl("/api/portfolio/current"), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch current portfolio: ${response.status}`);
  }
  return response.json();
}

export async function getPortfolioHistory(): Promise<PortfolioSnapshot[]> {
  const response = await fetch(backendUrl("/api/portfolio/history"), {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch portfolio history: ${response.status}`);
  }
  return response.json();
}
