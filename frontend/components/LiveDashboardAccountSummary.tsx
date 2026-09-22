"use client";

import { useEffect, useState } from "react";
import { formatCurrency } from "../lib/format";
import type { AccountSummary, PortfolioCurrent } from "../lib/types";

const REFRESH_INTERVAL_MS = 5_000;

export function LiveDashboardAccountSummary({ initialAccount }: { initialAccount: AccountSummary }) {
  const [account, setAccount] = useState(initialAccount);

  useEffect(() => {
    let isMounted = true;

    const refreshAccount = async () => {
      try {
        const response = await fetch("/api/portfolio/current", { cache: "no-store" });
        if (!response.ok) return;
        const portfolio = (await response.json()) as PortfolioCurrent;
        if (isMounted) setAccount(portfolio.account);
      } catch {
        // Keep displaying the most recently confirmed account values until the next successful poll.
      }
    };

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshAccount();
    }, REFRESH_INTERVAL_MS);

    return () => {
      isMounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const unrealizedClassName = account.unrealizedProfitLoss > 0
    ? "text-[#32e64d]"
    : account.unrealizedProfitLoss < 0
      ? "text-[#ff3b45]"
      : "text-neutral-100";
  const weeklyRealizedClassName = account.weeklyRealizedProfitLoss > 0
    ? "text-[#32e64d]"
    : account.weeklyRealizedProfitLoss < 0
      ? "text-[#ff3b45]"
      : "text-neutral-100";

  return (
    <section className="flex h-[72px] items-start justify-around gap-12" aria-label="Account overview">
      <article className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Total account value</p>
        <p className="mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight text-neutral-100 [font-variant-numeric:tabular-nums]">
          {formatCurrency(account.totalValue, account.currency)}
        </p>
      </article>
      <article className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Cash available</p>
        <p className="mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight text-neutral-100 [font-variant-numeric:tabular-nums]">
          {formatCurrency(account.cash.availableToTrade, account.currency)}
        </p>
      </article>
      <article className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Unrealised P/L</p>
        <p
          className={`mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight [font-variant-numeric:tabular-nums] ${unrealizedClassName}`}
        >
          {formatCurrency(Math.abs(account.unrealizedProfitLoss), account.currency)}
        </p>
      </article>
      <article className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Weekly gain</p>
        <p
          className={`mt-2 text-[clamp(2rem,3vw,2.5rem)] font-semibold tracking-tight [font-variant-numeric:tabular-nums] ${weeklyRealizedClassName}`}
        >
          {formatCurrency(Math.abs(account.weeklyRealizedProfitLoss), account.currency)}
        </p>
      </article>
    </section>
  );
}
