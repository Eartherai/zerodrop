// Semantic tones -> static Tailwind class strings (kept literal so Tailwind can see them).

import type { EventKind, RunStatus } from "../api/types";

export type Tone = "accent" | "success" | "danger" | "warning" | "info" | "plan" | "observe" | "llm" | "neutral";

interface ToneClasses {
  text: string;
  soft: string;
  border: string;
  dot: string;
  solid: string;
  ring: string;
}

export const TONES: Record<Tone, ToneClasses> = {
  accent: {
    text: "text-accent",
    soft: "bg-accent-soft",
    border: "border-accent",
    dot: "bg-accent",
    solid: "bg-accent text-on-accent",
    ring: "ring-accent",
  },
  success: {
    text: "text-success",
    soft: "bg-success-soft",
    border: "border-success",
    dot: "bg-success",
    solid: "bg-success text-surface",
    ring: "ring-success",
  },
  danger: {
    text: "text-danger",
    soft: "bg-danger-soft",
    border: "border-danger",
    dot: "bg-danger",
    solid: "bg-danger text-surface",
    ring: "ring-danger",
  },
  warning: {
    text: "text-warning",
    soft: "bg-warning-soft",
    border: "border-warning",
    dot: "bg-warning",
    solid: "bg-warning text-surface",
    ring: "ring-warning",
  },
  info: {
    text: "text-info",
    soft: "bg-info-soft",
    border: "border-info",
    dot: "bg-info",
    solid: "bg-info text-surface",
    ring: "ring-info",
  },
  plan: {
    text: "text-plan",
    soft: "bg-plan-soft",
    border: "border-plan",
    dot: "bg-plan",
    solid: "bg-plan text-surface",
    ring: "ring-plan",
  },
  observe: {
    text: "text-observe",
    soft: "bg-observe-soft",
    border: "border-observe",
    dot: "bg-observe",
    solid: "bg-observe text-surface",
    ring: "ring-observe",
  },
  llm: {
    text: "text-llm",
    soft: "bg-llm-soft",
    border: "border-llm",
    dot: "bg-llm",
    solid: "bg-llm text-surface",
    ring: "ring-llm",
  },
  neutral: {
    text: "text-neutral",
    soft: "bg-neutral-soft",
    border: "border-line-strong",
    dot: "bg-neutral",
    solid: "bg-neutral text-surface",
    ring: "ring-line-strong",
  },
};

/** CSS color used by the pulse animation (--zd-ring). */
export const TONE_VAR: Record<Tone, string> = {
  accent: "var(--zd-accent)",
  success: "var(--zd-success)",
  danger: "var(--zd-danger)",
  warning: "var(--zd-warning)",
  info: "var(--zd-info)",
  plan: "var(--zd-plan)",
  observe: "var(--zd-observe)",
  llm: "var(--zd-llm)",
  neutral: "var(--zd-neutral)",
};

export const KIND_TONE: Record<EventKind, Tone> = {
  state: "accent",
  plan: "plan",
  batch: "info",
  failure: "danger",
  recovery: "warning",
  decision: "observe",
  verify: "success",
  llm: "llm",
  info: "neutral",
};

export function statusTone(status: RunStatus | null): Tone {
  switch (status) {
    case "SUCCESS":
      return "success";
    case "PARTIAL_SUCCESS":
    case "RECOVERING":
    case "WAITING_FOR_APPROVAL":
      return "warning";
    case "FAILED":
      return "danger";
    case "EXECUTING":
      return "info";
    case "VERIFYING":
      return "accent";
    case "DISCOVERING":
    case "PLANNING":
    case "DRY_RUN":
      return "plan";
    default:
      return "neutral";
  }
}
