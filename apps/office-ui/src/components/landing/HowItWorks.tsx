const STEPS = [
  {
    number: '1',
    title: 'Dispatch',
    description:
      'Describe what you need. Agents auto-select the best team member and begin work.',
  },
  {
    number: '2',
    title: 'Collaborate',
    description:
      'Watch agents plan, implement, review, and iterate in the virtual office.',
  },
  {
    number: '3',
    title: 'Approve',
    description:
      'Review results, approve deployments, and watch your org grow autonomously.',
  },
];

export function HowItWorks() {
  return (
    <section className="mx-auto max-w-4xl px-4 py-24">
      <h2 className="pixel-text mb-14 text-center text-lg text-indigo-400">
        How It Works
      </h2>

      <div className="flex flex-col items-center gap-10 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        {STEPS.map((step, i) => (
          <div key={step.number} className="flex flex-1 flex-col items-center text-center">
            {/* Number badge */}
            <div className="pixel-border-accent mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-600/20">
              <span className="pixel-text text-sm text-indigo-400">{step.number}</span>
            </div>

            <h3 className="pixel-text mb-3 text-xs text-white">{step.title}</h3>

            <p className="max-w-xs text-sm leading-relaxed text-slate-400">
              {step.description}
            </p>

            {/* Arrow connector (desktop only) */}
            {i < STEPS.length - 1 && (
              <span
                className="mt-6 hidden text-2xl text-slate-600 sm:block"
                aria-hidden="true"
              >
                &rarr;
              </span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
