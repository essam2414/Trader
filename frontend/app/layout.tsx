// Root layout that wraps every page in the application. Loads the dashboard's
// two fonts (Inter for UI text, Roboto Mono for tabular financial figures)
// and applies the minimal dark theme base to <body>.
import type { Metadata } from "next";
import { Inter, Roboto_Mono } from "next/font/google";
import { AppShell } from "../components/AppShell";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const robotoMono = Roboto_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Trader Dashboard",
  description: "Swing trading portfolio dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${robotoMono.variable}`}>
      <body className="min-h-screen bg-neutral-950 font-sans text-neutral-100 antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
