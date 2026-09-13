import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Ludus editor',
  description: 'Author waves, sequence levels and configure a game against a Ludus engine.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
