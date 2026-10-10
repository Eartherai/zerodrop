import type { CSSProperties } from "react";
import { isTerminal, STAGE_LABELS, STAGES, type RunModel, type StageId } from "../lib/runModel";
import { TONE_VAR, TONES, type Tone } from "../lib/tones";

const STAGE_TONE: Record<StageId, Tone> = {
  goal: "accent",
  plan: "plan",
  action: "info",
  observation: "observe",
  failure: "danger",
  recovery: "warning",
  verification: "accent",
};

const STAGE_HINT: Record<StageId, string> = {
  goal: "Natural-language goal received",
  plan: "Discover APIs, infer mapping, dry-run",
  action: "Batched, idempotent writes",
  observation: "Read responses and progress",
  failure: "Classified: transient, contract, data…",
  recovery: "Backoff, lookup, replan, quarantine",
  verification: "Independent verifier decides",
};

function verificationTone(model: RunModel): Tone {
  if (model.verification === "success") return "success";
  if (model.verification === "partial") return "warning";
  if (model.verification === "failed") return "danger";
  return "accent";
}

function verificationLabel(model: RunModel): string | null {
  if (model.verification === "success") return "Verified: SUCCESS";
  if (model.verification === "partial") return "Verified: PARTIAL";
  if (model.verification === "failed") return "Verified: FAILED";
  return null;
}

function Arrow({ lit }: { lit: boolean }) {
  return (
    <li aria-hidden className="hidden shrink-0 items-center xl:flex">
      <svg viewBox="0 0 12 24" className={`h-6 w-3 ${lit ? "text-muted" : "text-line-strong"}`}>
        <path
          d="M2 4l7 8-7 8"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </li>
  );
}

function Stage({ id, model, index }: { id: StageId; model: RunModel; index: number }) {
  const stage = model.stages[id];
  const tone = id === "verification" ? verificationTone(model) : STAGE_TONE[id];
  const t = TONES[tone];
  const lit = stage.hits > 0;
  const finalVerdict = id === "verification" && model.verification !== null;
  const running = !isTerminal(model.status);
  const active = model.activeStages.includes(id) && (running || finalVerdict);
  const tags = Object.entries(stage.tags).sort((a, b) => b[1] - a[1]);
  const style = { "--zd-ring": TONE_VAR[tone] } as CSSProperties;
  const verdict = id === "verification" ? verificationLabel(model) : null;

  return (
    <li
      style={style}
      aria-current={active ? "step" : undefined}
      className={[
        "relative flex min-h-[7.5rem] min-w-0 flex-1 flex-col rounded-xl border-2 px-3 py-2.5 transition-colors duration-300",
        lit ? `${t.border} ${t.soft}` : "border-line bg-surface",
        active && running ? "zd-pulse" : "",
        finalVerdict ? `ring-2 ring-offset-2 ring-offset-bg ${t.ring}` : "",
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`text-xs font-bold tracking-widest uppercase ${lit ? t.text : "text-muted"}`}>
          <span className="mr-1.5 tabular opacity-70">{index + 1}</span>
          {STAGE_LABELS[id]}
        </span>
        {lit ? (
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-bold tabular ${t.solid}`}
            title={`${stage.hits} events`}
          >
            {stage.hits}
          </span>
        ) : null}
      </div>
      {verdict ? <p className={`mt-1 text-sm font-bold ${t.text}`}>{verdict}</p> : null}
      <p
        className={`mt-1 line-clamp-2 text-[0.8rem] leading-snug ${lit ? "text-fg" : "text-muted"}`}
        title={stage.lastMessage ?? STAGE_HINT[id]}
      >
        {stage.lastMessage ?? STAGE_HINT[id]}
      </p>
      {tags.length ? (
        <div className="mt-auto flex flex-wrap gap-1 pt-1.5">
          {tags.slice(0, 4).map(([tag, count]) => (
            <span
              key={tag}
              className={`rounded-md border px-1.5 py-px text-[0.7rem] font-semibold ${t.border} ${t.text} bg-surface`}
            >
              {tag} ×{count}
            </span>
          ))}
        </div>
      ) : null}
    </li>
  );
}

export function PipelineStrip({ model }: { model: RunModel }) {
  return (
    <nav aria-label="Agent pipeline">
      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:flex xl:items-stretch xl:gap-1">
        {STAGES.map((id, i) => (
          <PipelineItem key={id} id={id} index={i} model={model} />
        ))}
      </ol>
    </nav>
  );
}

function PipelineItem({ id, index, model }: { id: StageId; index: number; model: RunModel }) {
  return (
    <>
      {index > 0 ? <Arrow lit={model.stages[id].hits > 0} /> : null}
      <Stage id={id} model={model} index={index} />
    </>
  );
}
