"use client";
import { useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { initPostHog } from "@/lib/analytics/posthog";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    initPostHog();
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined" && window.posthog) {
      window.posthog.capture("$pageview");
    }
  }, [pathname, searchParams]);

  return <>{children}</>;
}
