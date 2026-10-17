import type { Vec2 } from "./scales";

export type ChartTone = "reference" | "baseline" | "candidate" | "s3" | "s4" | "s5" | "muted";

export interface ChartSeries {
  id: string;
  label: string;
  points: Vec2[];
  tone?: ChartTone;
  dashed?: boolean;
  markers?: boolean;
  unit?: string;
}

export interface ChartObstacle {
  id: string;
  label?: string;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  tone?: "stock" | "fixture" | "muted";
}

export interface ChartMarker {
  x: number;
  tone?: string;
  label?: string;
}

export const TONE_ORDER: ChartTone[] = ["reference", "baseline", "candidate", "s3", "s4", "s5"];

export function toneClass(tone: ChartTone | undefined, fallback: ChartTone): string {
  return `ax-tone-${tone ?? fallback}`;
}
