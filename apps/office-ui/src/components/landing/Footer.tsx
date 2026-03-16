export function Footer() {
  return (
    <footer className="border-t border-slate-800 px-4 py-8">
      <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-4 sm:flex-row">
        <span className="pixel-text text-[8px] text-slate-500">
          AutoSwarm Office
        </span>
        <div className="flex gap-6 text-sm text-slate-500">
          <a href="/login" className="transition-colors hover:text-indigo-400">
            Sign In
          </a>
          <a href="/demo" className="transition-colors hover:text-indigo-400">
            Demo
          </a>
        </div>
      </div>
    </footer>
  );
}
