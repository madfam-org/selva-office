const FEATURES = [
  {
    icon: '\u26A1',
    title: 'Dispatch Tasks',
    description:
      'Assign work to AI agents across coding, research, CRM, and deployment. Agents plan, execute, and push code autonomously.',
  },
  {
    icon: '\uD83D\uDC41\uFE0F',
    title: 'Observe in Real Time',
    description:
      'Watch your agents collaborate in a pixel-art virtual office. See task progress, agent status, and inter-agent communication live.',
  },
  {
    icon: '\u2713',
    title: 'Approve with Confidence',
    description:
      'Human-in-the-loop safety. Every destructive action, deployment, and external communication requires your explicit approval.',
  },
];

export function FeatureGrid() {
  return (
    <section className="mx-auto max-w-5xl px-4 py-24">
      <h2 className="pixel-text mb-14 text-center text-lg text-indigo-400">
        What You Can Do
      </h2>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature) => (
          <div
            key={feature.title}
            className="retro-panel group rounded-lg p-6 transition-transform hover:-translate-y-1"
          >
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-600/10 text-2xl">
              {feature.icon}
            </div>
            <h3 className="pixel-text mb-3 text-xs leading-relaxed text-indigo-300">
              {feature.title}
            </h3>
            <p className="text-sm leading-relaxed text-slate-400">
              {feature.description}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
