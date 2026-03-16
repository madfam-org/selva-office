const DEMO_ENABLED = process.env.NEXT_PUBLIC_DEMO_ENABLED !== 'false';

export function HeroSection() {
  return (
    <section className="relative flex min-h-screen flex-col items-center justify-center px-4 text-center">
      {/* Background grid lines */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(99,102,241,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(99,102,241,0.5) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
        }}
      />

      <h1 className="pixel-text animate-glow-pulse mb-6 text-2xl leading-relaxed text-indigo-400 sm:text-4xl">
        AutoSwarm Office
      </h1>

      <p className="mb-10 max-w-lg text-sm leading-relaxed text-slate-400 sm:text-base">
        Your AI team, working in a virtual office.
        <br />
        Dispatch tasks, watch agents collaborate in real-time, and approve every action.
      </p>

      <div className="flex flex-wrap items-center justify-center gap-4">
        {DEMO_ENABLED && (
          <a
            href="/demo"
            className="retro-btn rounded bg-indigo-600 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
          >
            Try Demo
          </a>
        )}
        <a
          href="/login"
          className="retro-btn rounded border border-slate-600 px-6 py-2.5 text-sm font-medium text-slate-300 transition-colors hover:border-slate-400 hover:text-white"
        >
          Sign In
        </a>
      </div>
    </section>
  );
}
