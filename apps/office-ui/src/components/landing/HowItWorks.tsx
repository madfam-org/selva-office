const STEPS = [
  {
    number: '1',
    title: 'Walk In',
    description:
      'Open selva.town. You land in a solarpunk pixel-art office. Your 10 agents are already at their desks, waiting for instructions.',
    color: 'emerald',
  },
  {
    number: '2',
    title: 'Dispatch',
    description:
      'Describe what you need in plain language. Selva picks the best agent, selects the right workflow graph, and starts executing.',
    color: 'amber',
  },
  {
    number: '3',
    title: 'Watch & Approve',
    description:
      'See your agents move between departments, write code, create PRs, send emails. Approve each action as it comes. Full transparency.',
    color: 'cyan',
  },
  {
    number: '4',
    title: 'Ship',
    description:
      'Code gets pushed, PRs get merged, invoices get filed, emails get sent. Your AI workforce delivered \u2014 and you approved every step.',
    color: 'purple',
  },
];

export function HowItWorks() {
  const COLORS: Record<string, string> = {
    emerald: 'bg-emerald-600/20 text-emerald-400',
    amber: 'bg-amber-600/20 text-amber-400',
    cyan: 'bg-cyan-600/20 text-cyan-400',
    purple: 'bg-purple-600/20 text-purple-400',
  };

  return (
    <section className="mx-auto max-w-5xl px-4 py-24">
      <h2 className="pixel-text mb-4 text-center text-lg text-emerald-400">
        How Selva Works
      </h2>
      <p className="mx-auto mb-14 max-w-lg text-center text-sm text-slate-500">
        From idea to shipped in four steps. You stay in control the entire time.
      </p>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((step) => (
          <div key={step.number} className="flex flex-col items-center text-center">
            <div className={`pixel-border-accent mb-5 flex h-14 w-14 items-center justify-center rounded-full ${COLORS[step.color]}`}>
              <span className="pixel-text text-sm">{step.number}</span>
            </div>
            <h3 className="pixel-text mb-3 text-xs text-white">{step.title}</h3>
            <p className="max-w-xs text-sm leading-relaxed text-slate-400">
              {step.description}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
