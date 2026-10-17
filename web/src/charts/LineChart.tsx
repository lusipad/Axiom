import { useId, useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import { extent, formatTick, makeProjection, niceTicks, pathFrom } from "./scales";
import { ChartLegend } from "./ChartLegend";
import type { ChartMarker, ChartSeries } from "./types";
import { toneClass } from "./types";

interface Hover {
  px: number;
  x: number;
  values: Array<{ label: string; value: number; tone?: string; unit?: string }>;
}

const WIDTH = 720;

export function LineChart({
  series,
  markers = [],
  ariaLabel,
  xLabel,
  yLabel,
  caption,
  legend = true,
  height = 300,
  wrapper = "svg",
  xFormat = formatTick,
}: {
  series: ChartSeries[];
  markers?: ChartMarker[];
  ariaLabel: string;
  xLabel?: string;
  yLabel?: string;
  caption?: string;
  legend?: boolean;
  height?: number;
  wrapper?: "svg" | "figure";
  xFormat?: (value: number) => string;
}) {
  const gridId = useId();
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<Hover | null>(null);

  const box = { width: WIDTH, height, left: 56, right: 20, top: 18, bottom: 34 };
  const projection = useMemo(() => {
    const xs = series.flatMap((item) => item.points.map(([x]) => x)).concat(markers.map((marker) => marker.x));
    const ys = series.flatMap((item) => item.points.map(([, y]) => y));
    const [minX, maxX] = extent(xs.length ? xs : [0, 1]);
    const [minY, maxY] = extent(ys.length ? ys : [0, 1]);
    const pad = (maxY - minY) * 0.08 || Math.abs(maxY) * 0.08 || 1;
    return makeProjection([minX, maxX], [minY - pad, maxY + pad], box);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series, markers, height]);

  const xTicks = niceTicks(projection.domainX[0], projection.domainX[1], 6);
  const yTicks = niceTicks(projection.domainY[0], projection.domainY[1], 5);

  const handleMove = (event: PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width === 0) return;
    const scale = WIDTH / rect.width;
    const px = (event.clientX - rect.left) * scale;
    const x = projection.invertX(px);
    const values = series.flatMap((item) => {
      if (item.points.length === 0) return [];
      let best = item.points[0]!;
      let bestDistance = Infinity;
      for (const point of item.points) {
        const distance = Math.abs(point[0] - x);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = point;
        }
      }
      return [{ label: item.label, value: best[1], tone: item.tone, unit: item.unit }];
    });
    if (values.length === 0) {
      setHover(null);
      return;
    }
    setHover({ px, x, values });
  };

  const plot = (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${WIDTH} ${height}`}
      role={wrapper === "svg" ? "img" : undefined}
      aria-label={wrapper === "svg" ? ariaLabel : undefined}
      aria-hidden={wrapper === "figure" ? true : undefined}
      onPointerMove={handleMove}
      onPointerLeave={() => setHover(null)}
    >
      <defs>
        <pattern id={gridId} width="32" height="32" patternUnits="userSpaceOnUse">
          <path d="M 32 0 L 0 0 0 32" className="ax-chart-grid-minor" fill="none" />
        </pattern>
      </defs>
      <rect width={WIDTH} height={height} fill={`url(#${gridId})`} />
      {xTicks.map((tick) => (
        <g key={`x-${tick}`}>
          <line className="ax-chart-grid" x1={projection.x(tick)} x2={projection.x(tick)} y1={box.top} y2={height - box.bottom} />
          <text className="ax-chart-tick" x={projection.x(tick)} y={height - box.bottom + 16} textAnchor="middle">{xFormat(tick)}</text>
        </g>
      ))}
      {yTicks.map((tick) => (
        <g key={`y-${tick}`}>
          <line className="ax-chart-grid" x1={box.left} x2={WIDTH - box.right} y1={projection.y(tick)} y2={projection.y(tick)} />
          <text className="ax-chart-tick" x={box.left - 8} y={projection.y(tick) + 3} textAnchor="end">{formatTick(tick)}</text>
        </g>
      ))}
      <line className="ax-chart-axis" x1={box.left} y1={height - box.bottom} x2={WIDTH - box.right} y2={height - box.bottom} />
      <line className="ax-chart-axis" x1={box.left} y1={box.top} x2={box.left} y2={height - box.bottom} />
      {xLabel && <text className="ax-chart-axis-label" x={WIDTH - box.right} y={height - 8} textAnchor="end">{xLabel}</text>}
      {yLabel && <text className="ax-chart-axis-label" x={box.left - 8} y={box.top + 4} textAnchor="end">{yLabel}</text>}
      {markers.map((marker, index) => (
        <g key={`${marker.x}-${index}`} className={`ax-chart-marker${marker.tone ? ` ax-marker-${marker.tone}` : ""}`}>
          <line x1={projection.x(marker.x)} x2={projection.x(marker.x)} y1={box.top} y2={height - box.bottom} />
          <circle cx={projection.x(marker.x)} cy={box.top} r={3} />
          {marker.label && <text x={projection.x(marker.x) + 4} y={box.top + 10}>{marker.label}</text>}
        </g>
      ))}
      {series.map((item) => (
        <g key={item.id} className={`ax-chart-series ${toneClass(item.tone, "muted")}`}>
          <path d={pathFrom(item.points, projection)} strokeDasharray={item.dashed ? "6 5" : undefined} />
          {item.markers && item.points.map(([x, y], index) => (
            <circle key={index} cx={projection.x(x)} cy={projection.y(y)} r={3} />
          ))}
        </g>
      ))}
      {hover && (
        <g className="ax-chart-crosshair" pointerEvents="none">
          <line x1={hover.px} x2={hover.px} y1={box.top} y2={height - box.bottom} />
        </g>
      )}
    </svg>
  );

  const overlay = hover && (
    <div
      className="ax-chart-tooltip"
      style={{ left: `${(hover.px / WIDTH) * 100}%`, top: "14px" }}
    >
      <strong>{xFormat(hover.x)}</strong>
      {hover.values.map((value) => (
        <span key={value.label} className={value.tone ? `ax-tooltip-${value.tone}` : undefined}>
          {value.label}: {formatTick(value.value)}{value.unit ? ` ${value.unit}` : ""}
        </span>
      ))}
    </div>
  );

  if (wrapper === "figure") {
    return (
      <figure className="ax-chart" role="img" aria-label={ariaLabel}>
        {plot}
        {overlay}
        {legend && <ChartLegend items={series.map((item) => ({ id: item.id, label: item.label, tone: item.tone, dashed: item.dashed }))} />}
        {caption && <figcaption className="ax-chart-caption">{caption}</figcaption>}
      </figure>
    );
  }
  return (
    <div className="ax-chart">
      {plot}
      {overlay}
      {legend && <ChartLegend items={series.map((item) => ({ id: item.id, label: item.label, tone: item.tone, dashed: item.dashed }))} />}
      {caption && <code className="ax-chart-caption">{caption}</code>}
    </div>
  );
}
