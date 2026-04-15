"use client";
import { useEffect } from "react";
import posthog from "posthog-js";
import { usePathname, useSearchParams } from "next/navigation";
import { initPostHog } from "@/lib/analytics/posthog";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    initPostHog();

    // Capture UTM parameters on first visit
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const utmSource = params.get("utm_source");
    if (utmSource && posthog.__loaded) {
      posthog.people.set_once({
        first_utm_source: utmSource,
        first_utm_medium: params.get("utm_medium") || undefined,
        first_utm_campaign: params.get("utm_campaign") || undefined,
      });
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined" && window.posthog) {
      window.posthog.capture("$pageview");
    }
  }, [pathname, searchParams]);

  return <>{children}</>;
}
