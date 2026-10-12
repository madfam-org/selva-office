import { render } from '@testing-library/react';
import { createElement } from 'react';
import { describe, expect, it } from 'vitest';

import {
  DEFAULT_ECOSYSTEM_PLATFORMS,
  EcosystemBanner,
  MADFAM_OWNED_DOMAINS,
  ecosystemLink,
  isOwnHost,
} from '@/vendor/ecosystem-banner';

describe('ecosystem banner links (2026-10-11 fix)', () => {
  it('links Forgesight to forgesight.app, never the retired forgesight.quest', () => {
    const urls = DEFAULT_ECOSYSTEM_PLATFORMS.map((p) => p.url);
    expect(urls).toContain('https://forgesight.app');
    expect(urls.some((u) => u.includes('forgesight.quest'))).toBe(false);
  });

  it('treats every default ticker destination as a MADFAM-owned host', () => {
    for (const p of DEFAULT_ECOSYSTEM_PLATFORMS) {
      expect(isOwnHost(new URL(p.url).hostname, MADFAM_OWNED_DOMAINS)).toBe(true);
    }
  });

  it('tags an own-site link with rel=noopener and the ecosystem UTM set', () => {
    const link = ecosystemLink('https://forgesight.app', {
      surface: 'banner',
      originHost: 'www.karafiel.mx',
      ownedDomains: MADFAM_OWNED_DOMAINS,
    });
    expect(link.rel).toBe('noopener');
    const url = new URL(link.href);
    expect(url.hostname).toBe('forgesight.app');
    expect(url.searchParams.get('utm_source')).toBe('karafiel.mx');
    expect(url.searchParams.get('utm_medium')).toBe('ecosystem');
    expect(url.searchParams.get('utm_campaign')).toBe('banner');
  });

  it('adds no UTM on the same host or from localhost', () => {
    for (const originHost of ['forgesight.app', 'localhost', '127.0.0.1', undefined]) {
      expect(
        ecosystemLink('https://forgesight.app', {
          surface: 'banner',
          originHost,
          ownedDomains: MADFAM_OWNED_DOMAINS,
        }),
      ).toEqual({ href: 'https://forgesight.app', rel: 'noopener' });
    }
  });

  it('keeps noreferrer and adds no UTM on a third-party link', () => {
    expect(
      ecosystemLink('https://github.com/madfam-org', {
        surface: 'banner',
        originHost: 'karafiel.mx',
        ownedDomains: MADFAM_OWNED_DOMAINS,
      }),
    ).toEqual({ href: 'https://github.com/madfam-org', rel: 'noopener noreferrer' });
  });
});

describe('EcosystemBanner rendered links', () => {
  it('renders own-site rel and the fixed Forgesight host (jsdom origin is localhost: no UTM)', () => {
    const { container } = render(createElement(EcosystemBanner, { forceVisible: true }));
    const anchors = [...container.querySelectorAll<HTMLAnchorElement>('.madfam-eco-banner a')];
    expect(anchors.length).toBe(DEFAULT_ECOSYSTEM_PLATFORMS.length * 2);
    for (const a of anchors) {
      expect(a.rel).toBe('noopener');
      expect(a.href).not.toContain('utm_');
      expect(a.href).not.toContain('forgesight.quest');
    }
    expect(anchors.some((a) => a.href.startsWith('https://forgesight.app'))).toBe(true);
  });
});
