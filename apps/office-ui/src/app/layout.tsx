import type { Metadata } from 'next';
import { Suspense } from 'react';
import { Inter, Press_Start_2P } from 'next/font/google';
import { JanuaProvider } from '@janua/nextjs-sdk';
import { PostHogProvider } from '@/components/PostHogProvider';
import { ServiceWorkerRegistrar } from '@/components/ServiceWorkerRegistrar';
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
      <head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#2a2218" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <link rel="apple-touch-icon" href="/assets/icons/icon-192.png" />
      </head>
      <body className="min-h-screen font-sans">
        <ServiceWorkerRegistrar />
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
