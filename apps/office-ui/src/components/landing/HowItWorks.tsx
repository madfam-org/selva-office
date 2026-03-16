const STEPS = [
  { number: '1', title: 'Dispatch a task', description: 'Describe what you need done and pick a graph type.' },
  { number: '2', title: 'Agents collaborate', description: 'Watch AI agents plan, code, test, and review in real-time.' },
  { number: '3', title: 'Review & approve', description: 'Every file write, git push, and deploy requires your approval.' },
];

export function HowItWorks() {
  return (
    <section className="mx-auto max-w-4xl px-4 py-24">
      <h2 className="pixel-text mb-12 text-center text-lg text-indigo-400">
        How It Works
      </h2>

      <div className="flex flex-col items-center gap-8 sm:flex-row sm:justify-between">
        {STEPS.map((step, i) => (
          <div key={step.number} className="flex flex-1 flex-col items-center text-center">
            <div className="pixel-border-accent mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-600/20">
              <span className="pixel-text text-sm text-indigo-400">{step.number}</span>
            </div>
            <h3 className="pixel-text mb-2 text-xs text-white">{step.title}</h3>
            <p className="text-sm leading-relaxed text-slate-400">{step.description}</p>
            {i < STEPS.length - 1 && (
              <span className="mt-4 hidden text-2xl text-slate-600 sm:block">→</span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
