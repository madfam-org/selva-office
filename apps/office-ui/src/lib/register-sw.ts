/**
 * Service worker registration for PWA support.
 * Import this module in a client component to register the service worker on page load.
 */
export function registerServiceWorker(): void {
  if (typeof window !== 'undefined' && 'serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {
        // Registration failed — silently ignore.
        // Common causes: localhost without HTTPS, or browser policy.
      });
    });
  }
}
