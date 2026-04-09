import { NextResponse } from 'next/server';

export async function GET() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return NextResponse.json({ status: 'ok', api: 'not-configured' });
  }
  try {
    const res = await fetch(`${apiUrl}/api/v1/health`, {
      signal: AbortSignal.timeout(3000),
    });
    return NextResponse.json({
      status: 'ok',
      api: res.ok ? 'connected' : 'degraded',
    });
  } catch {
    return NextResponse.json({ status: 'ok', api: 'unreachable' });
  }
}
