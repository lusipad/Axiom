import { useId, useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import { extent, formatTick, makeProjection, nearestPointIndex, niceTicks, pathFrom } from "./scales";
import { ChartLegend } from "./ChartLegend";
import type { ChartObstacle, ChartSeries, ChartTone } from "./types";
import { toneClass } from "./types";

interface Hover {
  px: number;
  py: number;
  seriesId: string;
  seriesLabel: string;
  tone?: string;
  x: number;
  y: number;
}

const WIDTH = 720;

export function XYChart({
  series,
  obstacles = [],
  ariaLabel,
  xLabel = "X",
  yLabel = "Y",
  caption,
  legend = true,
  equalAspect = true,
  height = 400,
}: {
  series: ChartSeries[];
  obstacles?: ChartObstacle[];
  ariaLabel: string;
  xLabel?: string;
  yLabel?: string;
  caption?: string;
  legend?: boolean;
  equalAspect?: boolean;
  height?: number;
}) {
  const gridId = useId();
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<Hover | null>(null);

  const box = { width: WIDTH, height, left: 56, right: 20, top: 18, bottom: 34 };
  const projection = useMemo(() => {
    const xs = series.flatMap((item) => item.points.map(([x]) => x))
      .concat(obstacles.flatMap((item) => [item.minX, item.maxX]));
    const ys = series.flatMap((item) => item.points.map(([, y]) => y))
      .concat(obstacles.flatMap((item) => [item.minY, item.maxY]));
    const [minX, maxX] = extent(xs.length ? xs : [0, 1]);
    const [minY, maxY] = extent(ys.length ? ys : [0, 1]);
    return makeProjection([minX, maxX], [minY, maxY], box, equalAspect);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series, obstacles, equalAspect, height]);

  const xTicks = niceTicks(projection.domainX[0], projection.domainX[1], 6);
  const yTicks = niceTicks(projection.domainY[0], projection.domainY[1], 5);

  const handleMove = (event: PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width === 0) return;
    const scale = WIDTH / rect.width;
    const px = (event.clientX - rect.left) * scale;
    const py = (event.clientY - rect.top) * scale;
    let best: Hover | null = null;
    let bestDistance = Infinity;
    for (const item of series) {
      if (item.points.length === 0) continue;
      const index = nearestPointIndex(item.points, px, py, projection);
      const [x, y] = item.points[index]!;
      const dx = projection.x(x) - px;
      const dy = projection.y(y) - py;
      const distance = dx * dx + dy * dy;
      if (distance < bestDistance) {
        bestDistance = distance;
        best = { px: projection.x(x), py: projection.y(y), seriesId: item.id, seriesLabel: item.label, tone: item.tone, x, y };
      }
    }
    setHover(best);
  };

  return (
    <div className="ax-chart">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${height}`}
        role="img"
        aria-label={ariaLabel}
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
            <text className="ax-chart-tick" x={projection.x(tick)} y={height - box.bottom + 16} textAnchor="middle">{formatTick(tick)}</text>
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
        <text className="ax-chart-axis-label" x={WIDTH - box.right} y={height - box.bottom + 16} textAnchor="end">{xLabel}</text>
        <text className="ax-chart-axis-label" x={box.left - 8} y={box.top + 4} textAnchor="end">{yLabel}</text>
        {obstacles.map((item) => {
          const x = projection.x(item.minX);
          const y = projection.y(item.maxY);
          const width = Math.max(projection.x(item.maxX) - x, 1);
          const h = Math.max(projection.y(item.minY) - y, 1);
          return (
            <g key={item.id} className={`ax-chart-obstacle ax-obstacle-${item.tone ?? "muted"}`}>
              <rect x={x} y={y} width={width} height={h} />
              {item.label && <text x={x + 5} y={y + 14}>{item.label}</text>}
            </g>
          );
        })}
        {series.map((item) => (
          <g key={item.id} className={`ax-chart-series ${toneClass(item.tone, "muted")}`}>
            <path d={pathFrom(item.points, projection)} strokeDasharray={item.dashed ? "6 5" : undefined} />
            {item.markers !== false && item.points.map(([x, y], index) => (
              <circle key={index} cx={projection.x(x)} cy={projection.y(y)} r={item.tone === "reference" ? 2.5 : 3.2} />
            ))}
          </g>
        ))}
        {hover && (
          <g className="ax-chart-crosshair" pointerEvents="none">
            <line x1={hover.px} x2={hover.px} y1={box.top} y2={height - box.bottom} />
            <line x1={box.left} x2={WIDTH - box.right} y1={hover.py} y2={hover.py} />
            <circle className={toneClass(hover.tone as ChartTone | undefined, "muted")} cx={hover.px} cy={hover.py} r={5} />
          </g>
        )}
      </svg>
      {hover && (
        <div
          className="ax-chart-tooltip"
          style={{
            left: `${(hover.px / WIDTH) * 100}%`,
            top: `${(hover.py / height) * 100}%`,
          }}
        >
          <strong>{hover.seriesLabel}</strong>
          <span>{xLabel} {formatTick(hover.x)}</span>
          <span>{yLabel} {formatTick(hover.y)}</span>
        </div>
      )}
      {legend && <ChartLegend items={series.map((item) => ({ id: item.id, label: item.label, tone: item.tone, dashed: item.dashed }))} />}
      {caption && <code className="ax-chart-caption">{caption}</code>}
    </div>
  );
}
