import type { MetadataRoute } from 'next';
import { buildSitemap } from '@/lib/seo/crawl';

export default function sitemap(): MetadataRoute.Sitemap {
  return buildSitemap();
}
