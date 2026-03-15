import type { Metadata } from 'next';
import { Suspense } from 'react';
import { Inter, Press_Start_2P } from 'next/font/google';
import { JanuaProvider } from '@janua/nextjs-sdk';
import { PostHogProvider } from '@/components/PostHogProvider';
import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

const pressStart2P = Press_Start_2P({
  weight: '400',
  subsets: ['latin'],
  variable: '--font-pixel',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'AutoSwarm Office',
  description: 'Gamified multi-agent business orchestration',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${pressStart2P.variable}`}>
      <body className="min-h-screen font-sans">
        <Suspense>
          <PostHogProvider>
            <JanuaProvider
              config={{ baseURL: process.env.NEXT_PUBLIC_JANUA_ISSUER_URL ?? '' }}
            >
              {children}
            </JanuaProvider>
          </PostHogProvider>
        </Suspense>
      </body>
    </html>
  );
}
