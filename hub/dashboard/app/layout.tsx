import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "JARVIS Hologram HUD",
  description: "Tactical hologram multi-agent operations console",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Sora:wght@400;600;700&display=swap"
          rel="stylesheet"
        />
        <meta name="theme-color" content="#03080f" />
      </head>
      <body>{children}</body>
    </html>
  );
}
