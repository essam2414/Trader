// Root layout that wraps every page in the application
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trader Dashboard",
  description: "Swing trading portfolio dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
