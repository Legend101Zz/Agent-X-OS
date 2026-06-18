import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent-X Operator Dashboard",
  description: "Mission-control dashboard for Agent-X kernel operations.",
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
