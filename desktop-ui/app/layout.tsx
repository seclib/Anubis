import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ANUBIS",
  description: "A calm AI workspace for chat, memory, notes, and documents.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
