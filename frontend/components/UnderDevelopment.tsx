export function UnderDevelopment({ title }: { title: string }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[1360px] items-center p-8 xl:p-10">
      <section className="w-full rounded-lg border border-zinc-800 bg-zinc-900 p-8">
        <span className="mb-4 inline-flex rounded-full border border-amber-500/20 bg-amber-500/10 px-3 py-1 font-mono text-xs font-medium uppercase tracking-wider text-amber-400">
          Coming soon
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">{title}</h1>
        <p className="mt-2 text-sm text-zinc-400">This area is under development.</p>
      </section>
    </main>
  );
}
