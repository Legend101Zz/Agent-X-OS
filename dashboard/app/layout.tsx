import type { Metadata } from "next";
import "./globals.css";
import "../src/components/ui/primitives.css";

export const metadata: Metadata = {
  title: "Agent-X Control Surface",
  description: "Mission-control surface for the Agent-X Business OS.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}