import { NextResponse } from 'next/server';

export async function GET() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return NextResponse.json({ status: 'ok' });
  }
  try {
    const res = await fetch(`${apiUrl}/api/v1/health`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) {
      return NextResponse.json({ status: 'degraded', api: 'unreachable' });
    }
    return NextResponse.json({ status: 'ok', api: 'connected' });
  } catch {
    return NextResponse.json({ status: 'degraded', api: 'unreachable' });
  }
}
