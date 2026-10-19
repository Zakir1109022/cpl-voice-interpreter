import "@livekit/components-styles";
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Bengali <-> English Meeting Interpreter",
  description: "Real-time translation powered by LiveKit Agents",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
