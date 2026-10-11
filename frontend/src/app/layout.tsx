import type { Metadata } from "next";
import { Inter, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

// Inter: a UI face with even word spacing at every size (globals.css turns on its cv11 / ss01 alternates)
const fontSans = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

const fontMono = IBM_Plex_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "MTA — Master Testing Agent",
  description: "Autonomous test generation, execution, and healing for your app.",
};

// Runs before first paint: restores the collapsed sidebar rail from the persisted UI store ("aqp-ui", see
// lib/stores/ui-store) so the rail width and content offset (CSS, keyed on html[data-sidebar]) never jump on load.
const SIDEBAR_STATE_SCRIPT = `try{var s=JSON.parse(localStorage.getItem("aqp-ui")||"null");document.documentElement.dataset.sidebar=s&&s.state&&s.state.sidebarCollapsed?"collapsed":"open"}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${fontSans.variable} ${fontMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: SIDEBAR_STATE_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
