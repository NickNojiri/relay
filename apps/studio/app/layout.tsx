import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Relay Studio",
  description: "Author, deploy, flag, and observe LLM prompts.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
