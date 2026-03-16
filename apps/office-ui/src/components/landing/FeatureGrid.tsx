const FEATURES = [
  {
    title: 'AI Agents',
    description: 'Autonomous agents across Engineering, Research, CRM, and Support departments.',
  },
  {
    title: 'Real-Time Collaboration',
    description: 'Proximity video, chat, emotes, and whiteboards in a shared virtual office.',
  },
  {
    title: 'Task Orchestration',
    description: 'Dispatch tasks and watch agents plan, implement, test, and push code.',
  },
  {
    title: 'Visual Workflows',
    description: 'Drag-and-drop workflow builder with 8 node types and conditional routing.',
  },
  {
    title: 'Human-in-the-Loop',
    description: 'Review and approve every agent action before it takes effect.',
  },
  {
    title: 'Full Observability',
    description: 'Real-time event stream, metrics dashboard, and task timeline views.',
  },
];

export function FeatureGrid() {
  return (
    <section className="mx-auto max-w-5xl px-4 py-24">
      <h2 className="pixel-text mb-12 text-center text-lg text-indigo-400">
        Features
      </h2>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature) => (
          <div
            key={feature.title}
            className="retro-panel rounded p-5 transition-transform hover:-translate-y-0.5"
          >
            <h3 className="pixel-text mb-2 text-xs text-indigo-300">
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
