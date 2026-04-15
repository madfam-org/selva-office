const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.selva.town';
const YEAR = new Date().getFullYear();

const LINKS = [
  { label: 'Office App', href: APP_URL },
  { label: 'Demo', href: `${APP_URL}/demo` },
  { label: 'API Docs', href: `${APP_URL}/api/v1/docs` },
  { label: 'GitHub', href: 'https://github.com/madfam-org' },
];

export function Footer() {
  return (
    <footer className="border-t border-slate-800/60 px-4 py-10">
      <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-6 sm:flex-row">
        {/* Left: branding */}
        <div className="text-center sm:text-left">
          <span className="pixel-text text-[8px] text-emerald-400/60">
            Selva
          </span>
          <p className="mt-1 text-xs text-slate-600">
            by Innovaciones MADFAM &middot; {YEAR}
          </p>
        </div>

        {/* Center: nav links */}
        <nav aria-label="Footer navigation">
          <ul className="flex flex-wrap items-center justify-center gap-6">
            {LINKS.map((link) => (
              <li key={link.label}>
                <a
                  href={link.href}
                  target={link.href.startsWith('http') ? '_blank' : undefined}
                  rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                  className="text-sm text-slate-500 transition-colors hover:text-indigo-400"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        {/* Right: status badge */}
        <a
          href="https://status.madfam.io"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-full border border-slate-700/60 px-3 py-1.5 text-xs text-slate-500 transition-colors hover:border-emerald-600/40 hover:text-emerald-400"
        >
          <span
            className="inline-block h-2 w-2 rounded-full bg-emerald-500"
            aria-hidden="true"
          />
          Status
        </a>
      </div>
    </footer>
  );
}
