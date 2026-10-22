import type { Metadata } from "next";
import { Inter, Fraunces, JetBrains_Mono } from "next/font/google";
import "@/styles/globals.css";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { LiveBackground } from "@/components/background/LiveBackground";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export const metadata: Metadata = {
  title: "RegulatorIQ | Banking & Financial Regulations Assistant",
  description:
    "Instant, verifiable, citation-backed intelligence on Reserve Bank of India circulars, Master Directions, and regulatory frameworks.",
  keywords: [
    "RBI",
    "Reserve Bank of India",
    "Banking Regulations",
    "Circulars",
    "Master Directions",
    "Compliance",
  ],
  authors: [{ name: "RegulatorIQ Team" }],
  robots: "index, follow",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${fraunces.variable} ${jetbrainsMono.variable}`}
    >
      <body className="min-h-screen bg-bg text-ink antialiased flex flex-col relative selection:bg-accent/25">
        <ThemeProvider>
          <LiveBackground />
          <div className="flex-1 flex flex-col relative z-10">{children}</div>
        </ThemeProvider>
      </body>
    </html>
  );
}
