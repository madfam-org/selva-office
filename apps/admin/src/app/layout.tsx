import type { Metadata } from 'next';
import { Suspense } from 'react';
import { Inter } from 'next/font/google';
import { JanuaProvider } from '@janua/nextjs-sdk';
import { PostHogProvider } from '@/components/PostHogProvider';
import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

export const metadata: Metadata = {
  title: 'Selva Admin',
  description: 'Administration panel for Selva',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
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
