const FEATURES = [
  {
    icon: '\u26A1',
    title: 'Dispatch Any Task',
    description:
      'Tell your agents what to build. They plan, write code, create PRs, run tests, and push to production \u2014 across 6 specialized workflow graphs.',
    color: 'emerald',
  },
  {
    icon: '\uD83C\uDFAE',
    title: 'Walk the Office',
    description:
      'A living pixel-art solarpunk office. Walk between departments, talk to agents, watch them work at their desks. Screen-share, video call, whiteboard together.',
    color: 'amber',
  },
  {
    icon: '\uD83D\uDEE1\uFE0F',
    title: 'Human-in-the-Loop',
    description:
      'Every file write, git push, email send, and deployment requires your explicit approval. Full audit trail. No surprises. You are always in command.',
    color: 'cyan',
  },
  {
    icon: '\uD83E\uDDE0',
    title: '54 Built-in Tools',
    description:
      'Email, calendar, SQL, HTTP, PDF, charts, image analysis, git, deployment, and more. Agents pick the right tool for each sub-task automatically.',
    color: 'purple',
  },
  {
    icon: '\uD83C\uDF10',
    title: 'Agent-to-Agent Protocol',
    description:
      'Agents discover and delegate to each other via A2A. External agents can connect too. Your office becomes a node in a larger intelligence mesh.',
    color: 'rose',
  },
  {
    icon: '\uD83C\uDFAF',
    title: 'Visual Workflow Builder',
    description:
      'Drag-and-drop workflow editor with conditional branching, loops, batch processing, and subgraphs. Design custom agent pipelines visually.',
    color: 'sky',
  },
];

const COLOR_MAP: Record<string, { bg: string; text: string; heading: string }> = {
  emerald: { bg: 'bg-emerald-600/10', text: 'text-emerald-400', heading: 'text-emerald-300' },
  amber: { bg: 'bg-amber-600/10', text: 'text-amber-400', heading: 'text-amber-300' },
  cyan: { bg: 'bg-cyan-600/10', text: 'text-cyan-400', heading: 'text-cyan-300' },
  purple: { bg: 'bg-purple-600/10', text: 'text-purple-400', heading: 'text-purple-300' },
  rose: { bg: 'bg-rose-600/10', text: 'text-rose-400', heading: 'text-rose-300' },
  sky: { bg: 'bg-sky-600/10', text: 'text-sky-400', heading: 'text-sky-300' },
};

export function FeatureGrid() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-24">
      <h2 className="pixel-text mb-4 text-center text-lg text-emerald-400">
        Everything Your Team Needs
      </h2>
      <p className="mx-auto mb-14 max-w-2xl text-center text-sm text-slate-500">
        Not a chatbot. Not an API wrapper. A full virtual office where AI agents live, collaborate, and build &mdash; with you as the decision-maker.
      </p>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature) => {
          const colors = COLOR_MAP[feature.color];
          return (
            <div
              key={feature.title}
              className="retro-panel group rounded-lg p-6 transition-transform hover:-translate-y-1"
            >
              <div className={`mb-4 flex h-12 w-12 items-center justify-center rounded-lg ${colors.bg} text-2xl`}>
                {feature.icon}
              </div>
              <h3 className={`pixel-text mb-3 text-xs leading-relaxed ${colors.heading}`}>
                {feature.title}
              </h3>
              <p className="text-sm leading-relaxed text-slate-400">
                {feature.description}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
