import type { MetadataRoute } from 'next';
import { getSiteConfig, type SiteConfig } from '@/lib/site-config';

/**
 * Crawl files. middleware.ts adds them to its public paths so the auth
 * redirect never answers them with the login page.
 */
export const CRAWL_FILE_PATHS = ['/robots.txt', '/sitemap.xml', '/llms.txt'] as const;

/** Public marketing pages listed in the sitemap: app/page.tsx and app/pricing. */
export const SITEMAP_PATHS = ['/', '/pricing'] as const;

/** Public but not listed: the interactive demo is a client-rendered office. */
export const PUBLIC_UNLISTED_PATHS = ['/demo'] as const;

/**
 * App, auth and API routes that exist on the marketing host. Every top-level
 * route under src/app must be in SITEMAP_PATHS, PUBLIC_UNLISTED_PATHS or here
 * (enforced by src/__tests__/crawl-files.test.ts).
 */
export const MARKETING_DISALLOW = [
  '/api/',
  '/artifacts',
  '/atrium',
  '/bundles',
  '/catalog',
  '/dragon-eggs',
  '/guest',
  '/jumanji',
  '/login',
  '/office',
  '/onboarding',
  '/settings',
  '/status',
] as const;

function originOf(url: string): string {
  return new URL(url).origin;
}

export function buildSitemap(config: SiteConfig = getSiteConfig()): MetadataRoute.Sitemap {
  const origin = originOf(config.marketingUrl);
  return SITEMAP_PATHS.map((path) => ({
    url: `${origin}${path}`,
    changeFrequency: 'weekly',
    priority: path === '/' ? 1 : 0.8,
  }));
}

/**
 * One office-ui deployment serves both selva.town and app.selva.town. Only
 * the marketing host gets real rules and a Sitemap line. The app host, and
 * any deployment where the marketing and app hosts are the same (staging,
 * local), is closed to crawlers.
 */
export function buildRobots(
  requestHost: string,
  config: SiteConfig = getSiteConfig(),
): MetadataRoute.Robots {
  const marketingHost = new URL(config.marketingUrl).host;
  const appHost = new URL(config.appUrl).host;
  const servesMarketing = requestHost === marketingHost && marketingHost !== appHost;

  if (!servesMarketing) {
    return { rules: { userAgent: '*', disallow: '/' } };
  }

  return {
    rules: { userAgent: '*', allow: '/', disallow: [...MARKETING_DISALLOW] },
    sitemap: `${originOf(config.marketingUrl)}/sitemap.xml`,
  };
}

/**
 * Public llms.txt (llmstxt.org convention). Facts come from the landing copy
 * (app/page.tsx, components/landing). Prices are never typed here; the file
 * links to the pricing page.
 */
export function buildLlmsTxt(config: SiteConfig = getSiteConfig()): string {
  const marketing = originOf(config.marketingUrl);
  const app = originOf(config.appUrl);
  return [
    '# Selva',
    '',
    '> Selva is an AI workforce that lives in a virtual office. Ten specialized agents plan, code, research, file and deploy, while every file write, git push, email send and deployment waits for your explicit approval, with a full audit trail. You can walk into the live demo without an account. Selva is built by Innovaciones MADFAM.',
    '',
    '## Links',
    '',
    `- [Home](${marketing}/): what Selva is and how it works.`,
    `- [Pricing](${marketing}/pricing): current plans.`,
    `- [Live demo](${app}/demo): walk in, dispatch a task and watch it happen; no account needed.`,
    '- [Contact](https://madfam.io/en/contact): Innovaciones MADFAM contact page.',
    '',
  ].join('\n');
}
