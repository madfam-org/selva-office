import type { MetadataRoute } from 'next';
import { headers } from 'next/headers';
import { buildRobots } from '@/lib/seo/crawl';

export default async function robots(): Promise<MetadataRoute.Robots> {
  const requestHeaders = await headers();
  return buildRobots(requestHeaders.get('host') || '');
}
