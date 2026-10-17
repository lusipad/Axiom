import type { ChartTone } from "./types";

export interface LegendItem {
  id: string;
  label: string;
  tone?: ChartTone | string;
  dashed?: boolean;
}

export function ChartLegend({ items, ariaLabel = "图例" }: { items: LegendItem[]; ariaLabel?: string }) {
  if (items.length === 0) return null;
  return (
    <div className="ax-chart-legend" aria-label={ariaLabel}>
      {items.map((item) => (
        <span key={item.id} className={item.tone ? `ax-legend-${item.tone}` : undefined}>
          <i className={item.dashed ? "dashed" : undefined} />
          {item.label}
        </span>
      ))}
    </div>
  );
}
