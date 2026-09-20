"use client";

import { usePathname } from "next/navigation";
import { SessionHistoryGuard } from "./SessionHistoryGuard";
import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login") {
    return children;
  }

  return (
    <div className="mx-auto grid min-h-screen w-full min-w-[1024px] max-w-[1680px] grid-cols-[14.5rem_minmax(0,1fr)] border-x border-neutral-800 bg-neutral-950 shadow-2xl shadow-black/20">
      <SessionHistoryGuard />
      <Sidebar />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
