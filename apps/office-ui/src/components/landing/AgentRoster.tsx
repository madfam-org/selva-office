const AGENTS = [
  { name: 'Or\u00E1culo', role: 'Strategic Advisor', level: 10, dept: 'Executive Brain Trust', color: '#7c7ff7' },
  { name: 'Centinela', role: 'Chief of Staff', level: 9, dept: 'Executive Brain Trust', color: '#7c7ff7' },
  { name: 'Forjador', role: 'CTO', level: 10, dept: 'Executive Brain Trust', color: '#7c7ff7' },
  { name: 'Telar', role: 'Product Owner', level: 7, dept: 'Build & Run Engine', color: '#67e8f9' },
  { name: 'C\u00F3dice', role: 'Lead Developer', level: 9, dept: 'Build & Run Engine', color: '#67e8f9' },
  { name: 'Vig\u00EDa', role: 'SRE', level: 8, dept: 'Build & Run Engine', color: '#67e8f9' },
  { name: 'Heraldo', role: 'Growth Director', level: 8, dept: 'Growth & Market', color: '#f472b6' },
  { name: 'Nexo', role: 'CRM Lead', level: 8, dept: 'Growth & Market', color: '#f472b6' },
  { name: '\u00C1ureo', role: 'Finance Controller', level: 7, dept: 'Physical-Digital Bridge', color: '#fbbf24' },
  { name: 'Espectro', role: 'MES Supervisor', level: 7, dept: 'Physical-Digital Bridge', color: '#fbbf24' },
];

export function AgentRoster() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-24">
      <h2 className="pixel-text mb-14 text-center text-lg text-indigo-400">
        Meet Your AI Team
      </h2>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
        {AGENTS.map((agent) => (
          <div
            key={agent.name}
            className="retro-panel flex flex-col items-center rounded-lg p-4 text-center transition-transform hover:-translate-y-1"
          >
            {/* Agent avatar placeholder */}
            <div
              className="mb-3 flex h-10 w-10 items-center justify-center rounded-full text-lg font-bold text-slate-950"
              style={{ backgroundColor: agent.color }}
              aria-hidden="true"
            >
              {agent.name.charAt(0)}
            </div>

            <h3 className="pixel-text mb-1 text-[8px] leading-relaxed text-white">
              {agent.name}
            </h3>

            <p className="mb-2 text-xs text-slate-400">
              {agent.role}
            </p>

            {/* Level badge */}
            <span className="mb-2 inline-block rounded bg-slate-700/60 px-2 py-0.5 text-[10px] text-slate-300">
              Lv.{agent.level}
            </span>

            {/* Department badge */}
            <span
              className="inline-block rounded-full px-2 py-0.5 text-[9px] font-medium"
              style={{
                backgroundColor: `${agent.color}20`,
                color: agent.color,
                border: `1px solid ${agent.color}40`,
              }}
            >
              {agent.dept}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
