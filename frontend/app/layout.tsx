// Root layout that wraps every page in the application. Loads the dashboard's
// two fonts (Manrope for UI text, JetBrains Mono for tabular financial
// figures) and applies the dark theme base to <body>.
import type { Metadata } from "next";
import { JetBrains_Mono, Manrope } from "next/font/google";
import { Sidebar } from "../components/Sidebar";
import "./globals.css";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const jetbrainsMono = JetBrains_Mono({
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
    <html lang="en" className={`${manrope.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen bg-zinc-950 font-sans text-zinc-100 antialiased">
        <div className="mx-auto grid min-h-screen w-full min-w-[1024px] max-w-[1680px] grid-cols-[14.5rem_minmax(0,1fr)] border-x border-zinc-900 bg-zinc-950 shadow-2xl shadow-black/20">
          <Sidebar />
          <div className="min-w-0">{children}</div>
        </div>
      </body>
    </html>
  );
}
