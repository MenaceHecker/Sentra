import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-20">
      <section className="text-center">
        <h1 className="text-5xl font-bold tracking-tight">Sentra</h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600">
          Connect your system&apos;s logs, metrics, and runbooks. When something
          breaks, Sentra investigates, shows its evidence, and — with your
          approval — takes the safe next step.
        </p>
        <div className="mt-8 flex justify-center gap-4">
          <Link
            href="/dashboard"
            className="rounded-md bg-slate-900 px-5 py-2.5 text-white hover:bg-slate-700"
          >
            View live demo
          </Link>
          <a
            href="https://github.com/MenaceHecker/Sentra"
            className="rounded-md border border-slate-300 px-5 py-2.5 text-slate-700 hover:bg-slate-50"
          >
            GitHub
          </a>
        </div>
      </section>

      <section className="mt-20">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          How it works
        </h2>
        <div className="mt-4 grid gap-6 sm:grid-cols-3">
          <div className="rounded-lg border border-slate-200 p-5">
            <div className="text-sm font-medium text-slate-900">1. Investigate</div>
            <p className="mt-2 text-sm text-slate-600">
              The agent calls read-only tools, logs, metrics, deploy history,
              runbooks, autonomously, and builds a root-cause hypothesis it
              cites to specific evidence.
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 p-5">
            <div className="text-sm font-medium text-slate-900">2. Propose</div>
            <p className="mt-2 text-sm text-slate-600">
              If the evidence justifies it, the agent proposes a fix, a
              rollback or a restart. Proposing is as far as it goes on its
              own.
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 p-5">
            <div className="text-sm font-medium text-slate-900">3. Approve</div>
            <p className="mt-2 text-sm text-slate-600">
              A human reviews the evidence and approves or rejects. Nothing
              side-effecting ever runs without that step, enforced in code,
              not by asking the model nicely.
            </p>
          </div>
        </div>
      </section>

      <section className="mt-16 rounded-lg border border-slate-200 bg-slate-50 p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Example hypothesis
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-700">
          &ldquo;The checkout service is returning 500 errors due to a missing{" "}
          <code className="rounded bg-slate-200 px-1">shipping_method</code>{" "}
          field in incoming requests, introduced by deploy{" "}
          <code className="rounded bg-slate-200 px-1">bf10a95</code> three
          minutes before the error spike. This matches the known issue
          documented in the Checkout Service runbook.&rdquo;
        </p>
        <p className="mt-2 text-xs font-medium text-slate-500">Confidence: high</p>
      </section>

      <section className="mt-16">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Architecture
        </h2>
        <p className="mt-3 text-sm text-slate-600">
          Next.js talks only to the FastAPI backend. The backend ingests from
          a simulated system (logs, metrics, deploys), stores runbooks in
          pgvector, and runs the agent loop with native LLM tool-calling. The
          read-only vs. side-effecting distinction, and the approval gate, are
          enforced in the backend&apos;s orchestration layer, never in a
          prompt. See the{" "}
          <a
            href="https://github.com/MenaceHecker/Sentra/blob/main/docs/spec.md"
            className="underline"
          >
            full spec
          </a>{" "}
          for the design.
        </p>
      </section>
    </main>
  );
}
