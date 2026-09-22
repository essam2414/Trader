"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  label: string;
  icon: React.ReactNode;
};

const iconClassName = "h-[18px] w-[18px] shrink-0";

const navigation: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={iconClassName} aria-hidden="true"><path d="M4 13h6V4H4v9Zm0 7h6v-4H4v4Zm10 0h6v-9h-6v9Zm0-16v4h6V4h-6Z" /></svg>,
  },
  {
    href: "/history",
    label: "History",
    icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={iconClassName} aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7" /><path d="M3 4v5h5m4-4v7l4 2" /></svg>,
  },
  {
    href: "/account",
    label: "Account",
    icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={iconClassName} aria-hidden="true"><circle cx="12" cy="8" r="3.5" /><path d="M4.5 20c.8-3.8 3.5-5.8 7.5-5.8s6.7 2 7.5 5.8" /></svg>,
  },
];

const settingsNavigation: NavItem = {
  href: "/settings",
  label: "Settings",
  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={iconClassName} aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.1 2.1-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.2h-3v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1-2.1-2.1.1-.1A1.7 1.7 0 0 0 7 15a1.7 1.7 0 0 0-1.5-1H5.3v-3h.2A1.7 1.7 0 0 0 7 10a1.7 1.7 0 0 0-.3-1.9l-.1-.1 2.1-2.1.1.1A1.7 1.7 0 0 0 10.7 6a1.7 1.7 0 0 0 1-1.5v-.2h3v.2a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1 2.1 2.1-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.2v3h-.2a1.7 1.7 0 0 0-1.5 1.4Z" /></svg>,
};

function SidebarLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const isActive = pathname === item.href;

  return (
    <li>
      <Link
        href={item.href}
        aria-current={isActive ? "page" : undefined}
        className={`flex min-h-14 items-center gap-4 rounded-xl px-4 py-3 text-base font-medium transition-all ${
          isActive
            ? "bg-neutral-300 text-neutral-950 shadow-lg shadow-black/20"
            : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-100"
        }`}
      >
        {item.icon}
        {item.label}
      </Link>
    </li>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 flex h-screen flex-col border-r border-neutral-800 bg-neutral-950 px-5 py-6">
      <Link href="/" className="mb-6 px-4" aria-label="Invest account">
        <span className="text-3xl font-bold tracking-tight text-neutral-100">Invest</span>
      </Link>

      <nav aria-label="Main navigation">
        <ul className="space-y-3">
          {navigation.map((item) => <SidebarLink key={item.href} item={item} pathname={pathname} />)}
        </ul>
      </nav>

      <nav className="-mx-5 mt-auto border-t border-neutral-800 px-5 pt-5" aria-label="Application settings">
        <ul>
          <SidebarLink item={settingsNavigation} pathname={pathname} />
        </ul>
      </nav>
    </aside>
  );
}
