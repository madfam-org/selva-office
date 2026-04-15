const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.selva.town';

export function HeroSection() {
  return (
    <section className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 text-center">
      {/* Animated background grid */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        aria-hidden="true"
        style={{
          backgroundImage:
            'linear-gradient(rgba(99,102,241,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(99,102,241,0.5) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
        }}
      />

      {/* Floating particle dots (CSS-only) */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="landing-particle" style={{ left: '10%', top: '20%', animationDelay: '0s', animationDuration: '6s' }} />
        <div className="landing-particle" style={{ left: '25%', top: '70%', animationDelay: '1.2s', animationDuration: '7s' }} />
        <div className="landing-particle" style={{ left: '45%', top: '15%', animationDelay: '2.4s', animationDuration: '5.5s' }} />
        <div className="landing-particle" style={{ left: '60%', top: '80%', animationDelay: '0.8s', animationDuration: '6.5s' }} />
        <div className="landing-particle" style={{ left: '75%', top: '35%', animationDelay: '3.2s', animationDuration: '7.5s' }} />
        <div className="landing-particle" style={{ left: '90%', top: '55%', animationDelay: '1.6s', animationDuration: '5s' }} />
        <div className="landing-particle" style={{ left: '35%', top: '45%', animationDelay: '4s', animationDuration: '6.8s' }} />
        <div className="landing-particle" style={{ left: '80%', top: '10%', animationDelay: '2s', animationDuration: '5.8s' }} />
      </div>

      <h1
        className="pixel-text animate-glow-pulse mb-6 bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-2xl leading-relaxed text-transparent sm:text-4xl"
      >
        AutoSwarm Office
      </h1>

      <p className="mb-4 max-w-lg text-base leading-relaxed text-slate-300 sm:text-lg">
        Your AI team, working in a virtual office.
      </p>

      <p className="mb-10 max-w-2xl text-sm leading-relaxed text-slate-400 sm:text-base">
        Dispatch tasks, watch agents collaborate in real-time, and approve every action.
      </p>

      {/* Metrics line */}
      <div className="mb-10 flex flex-wrap items-center justify-center gap-x-3 gap-y-2 text-xs text-slate-500 sm:text-sm">
        <span className="text-indigo-400">10 AI Agents</span>
        <span aria-hidden="true">&#x2022;</span>
        <span className="text-purple-400">4 Departments</span>
        <span aria-hidden="true">&#x2022;</span>
        <span className="text-cyan-400">Real-Time Collaboration</span>
        <span aria-hidden="true">&#x2022;</span>
        <span className="text-amber-400">HITL Safety</span>
      </div>

      {/* CTAs */}
      <div className="flex flex-wrap items-center justify-center gap-4">
        <a
          href={APP_URL}
          className="retro-btn pixel-border-accent rounded bg-indigo-600 px-8 py-3 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
        >
          Enter the Office &rarr;
        </a>
        <a
          href={`${APP_URL}/demo`}
          className="retro-btn rounded border border-slate-600 px-8 py-3 text-sm font-medium text-slate-300 transition-colors hover:border-indigo-500 hover:text-white"
        >
          Try Demo
        </a>
      </div>
    </section>
  );
}
