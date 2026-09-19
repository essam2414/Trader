// Error boundary for the dashboard route (Next.js App Router convention).
// Shown when the dashboard fails to load - most commonly because the backend
// can't reach Trading212 (missing/invalid API credentials, surfaced by the
// backend as a 502), or because the backend server itself isn't reachable.
"use client";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const isTrading212Unreachable = error.message.includes("502");

  return (
    <main className="mx-auto max-w-2xl space-y-4 p-8 text-center">
      <h1 className="text-2xl font-bold">Couldn&apos;t load your portfolio</h1>
      {isTrading212Unreachable ? (
        <p className="text-neutral-600">
          The backend couldn&apos;t connect to Trading212. Check that{" "}
          <code className="rounded bg-neutral-100 px-1">TRADING212_API_KEY</code> and{" "}
          <code className="rounded bg-neutral-100 px-1">TRADING212_API_SECRET</code> in{" "}
          <code className="rounded bg-neutral-100 px-1">backend/.env</code> are set to real,
          valid Trading212 API credentials.
        </p>
      ) : (
        <p className="text-neutral-600">
          Something went wrong loading your data. Make sure the backend server is running and
          reachable at the configured{" "}
          <code className="rounded bg-neutral-100 px-1">BACKEND_URL</code>.
        </p>
      )}
      <button
        onClick={() => reset()}
        className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
      >
        Try again
      </button>
    </main>
  );
}
