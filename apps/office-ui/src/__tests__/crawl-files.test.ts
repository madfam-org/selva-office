import { readdirSync } from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';
import { NextRequest } from 'next/server';
import { middleware } from '../middleware';
import {
  CRAWL_FILE_PATHS,
  MARKETING_DISALLOW,
  PUBLIC_UNLISTED_PATHS,
  SITEMAP_PATHS,
  buildLlmsTxt,
  buildRobots,
  buildSitemap,
} from '@/lib/seo/crawl';

const PROD = { appUrl: 'https://app.selva.town', marketingUrl: 'https://selva.town' };
const STAGING = {
  appUrl: 'https://staging.selva.town',
  marketingUrl: 'https://staging.selva.town',
};

function req(url: string, host: string): NextRequest {
  return new NextRequest(new URL(url), { headers: { host } });
}

describe('crawl files reach the app instead of the login redirect (J1 F8)', () => {
  for (const crawlPath of CRAWL_FILE_PATHS) {
    it(`passes ${crawlPath} through on selva.town and app.selva.town`, () => {
      for (const host of ['selva.town', 'app.selva.town']) {
        const res = middleware(req(`https://${host}${crawlPath}`, host));
        expect(res.headers.get('location')).toBeNull();
      }
    });

    it(`still 301s www.selva.town${crawlPath} to the apex`, () => {
      const res = middleware(req(`https://www.selva.town${crawlPath}`, 'www.selva.town'));
      expect(res.status).toBe(301);
      expect(new URL(res.headers.get('location')!).host).toBe('selva.town');
    });
  }

  it('keeps app routes behind the login redirect', () => {
    const res = middleware(req('https://selva.town/office', 'selva.town'));
    expect(new URL(res.headers.get('location')!).pathname).toBe('/login');
  });
});

describe('robots', () => {
  it('gives selva.town real rules and a Sitemap line', () => {
    const robots = buildRobots('selva.town', PROD);
    expect(robots.sitemap).toBe('https://selva.town/sitemap.xml');
    expect(robots.rules).toEqual({ userAgent: '*', allow: '/', disallow: [...MARKETING_DISALLOW] });
  });

  it('closes app.selva.town and unknown hosts', () => {
    for (const host of ['app.selva.town', 'admin.selva.town', '']) {
      const robots = buildRobots(host, PROD);
      expect(robots.rules).toEqual({ userAgent: '*', disallow: '/' });
      expect(robots.sitemap).toBeUndefined();
    }
  });

  it('closes staging, where the marketing and app hosts are the same', () => {
    expect(buildRobots('staging.selva.town', STAGING).rules).toEqual({
      userAgent: '*',
      disallow: '/',
    });
  });

  it('classifies every top-level route as listed, public-unlisted or disallowed', () => {
    const appDir = path.resolve(__dirname, '../app');
    const routes = readdirSync(appDir, { withFileTypes: true })
      .filter(
        (entry) => entry.isDirectory() && !entry.name.startsWith('(') && !entry.name.includes('.'),
      )
      .map((entry) => `/${entry.name}`);
    const known = new Set<string>([
      ...SITEMAP_PATHS,
      ...PUBLIC_UNLISTED_PATHS,
      ...MARKETING_DISALLOW.map((p) => p.replace(/\/$/, '')),
    ]);
    expect(routes.filter((route) => !known.has(route))).toEqual([]);
  });
});

describe('sitemap', () => {
  it('lists only public marketing pages, absolute on selva.town', () => {
    expect(buildSitemap(PROD).map((entry) => entry.url)).toEqual([
      'https://selva.town/',
      'https://selva.town/pricing',
    ]);
  });
});

describe('llms.txt', () => {
  it('follows the convention and stays public', () => {
    const llms = buildLlmsTxt(PROD);
    expect(llms.startsWith('# Selva\n')).toBe(true);
    expect(llms).toMatch(/^> /m);
    expect(llms).toContain('## Links');
    expect(llms).toContain('(https://selva.town/pricing)');
    expect(llms).toContain('(https://app.selva.town/demo)');
    expect(llms).not.toMatch(/\$\s?\d|MXN|USD/);
    expect(llms).not.toMatch(/admin\.|api\.selva|gw\.selva|inference\.|localhost|svc\.cluster/);
  });
});
