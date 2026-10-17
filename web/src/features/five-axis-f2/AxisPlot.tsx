import { useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import { extent, formatTick, makeProjection, niceTicks, pathFrom } from "../../charts";
import type { JointPolynomialSegment, MachineAxis } from "./types";

const COLORS = [
  "var(--chart-series-3)",
  "var(--chart-series-4)",
  "var(--chart-series-5)",
  "var(--chart-baseline)",
  "var(--chart-candidate)",
];
const TONES = ["s3", "s4", "s5", "baseline", "candidate"];
const SIGMA_TICKS = [0, 0.25, 0.5, 0.75, 1];
const WIDTH = 720;
const LEFT = 54;
const RIGHT = 22;
const TOP = 20;
const BOTTOM = 40;
const ROW_HEIGHT = 54;
const ROW_PAD = 9;

interface HoverValue {
  axisId: string;
  value: number;
  unit: string;
  tone: string;
  y: number;
}

function evaluate(segment: JointPolynomialSegment, sigma: number, axisIndex: number): number {
  const span = segment.sigmaEnd - segment.sigmaStart;
  const local = span === 0 ? 0 : (sigma - segment.sigmaStart) / span;
  return segment.coefficients.reduce(
    (sum, coefficient, power) => sum + (coefficient[axisIndex] ?? 0) * local ** power,
    0,
  );
}
function samples(segments: JointPolynomialSegment[], axisIndex: number): Array<[number, number]> {
  return segments.flatMap((segment, segmentIndex) => Array.from({ length: 25 }, (_, index) => {
    if (segmentIndex > 0 && index === 0) return null;
    const sigma = segment.sigmaStart + (segment.sigmaEnd - segment.sigmaStart) * index / 24;
    return [sigma, evaluate(segment, sigma, axisIndex)] as [number, number];
  }).filter((item): item is [number, number] => item !== null));
}

export function AxisPlot({ axes, segments }: { axes: MachineAxis[]; segments: JointPolynomialSegment[] }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<{ px: number; sigma: number; values: HoverValue[] } | null>(null);

  const { rows, xProjection, height } = useMemo(() => {
    const plotHeight = TOP + ROW_HEIGHT * axes.length + BOTTOM;
    const sampled = axes.map((axis, index) => ({
      axis,
      index,
      values: samples(segments, index),
      color: COLORS[index % COLORS.length]!,
      tone: TONES[index % TONES.length] ?? "muted",
    }));
    const sigmas = sampled.flatMap((row) => row.values.map(([sigma]) => sigma));
    const domainX = extent(sigmas.length ? sigmas : [0, 1]);
    const xBox = { width: WIDTH, height: plotHeight, left: LEFT, right: RIGHT, top: TOP, bottom: BOTTOM };
    const rows = sampled.map((row) => {
      const [min, max] = extent(row.values.map(([, value]) => value));
      const padY = (max - min) * 0.12 || Math.abs(max) * 0.12 || 1;
      const rowTop = TOP + row.index * ROW_HEIGHT;
      const projection = makeProjection(domainX, [min - padY, max + padY], {
        width: WIDTH,
        height: plotHeight,
        left: LEFT,
        right: RIGHT,
        top: rowTop + ROW_PAD,
        bottom: plotHeight - (rowTop + ROW_HEIGHT - ROW_PAD),
      });
      const ticks = niceTicks(min, max, 3);
      return {
        ...row,
        projection,
        baseline: rowTop + ROW_HEIGHT / 2,
        rangeLow: ticks[0] ?? min,
        rangeHigh: ticks[ticks.length - 1] ?? max,
      };
    });
    return { rows, xProjection: makeProjection(domainX, [0, 1], xBox), height: plotHeight };
  }, [axes, segments]);

  const handleMove = (event: PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg || rows.length === 0) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width === 0) return;
    const px = (event.clientX - rect.left) * (WIDTH / rect.width);
    const sigma = xProjection.invertX(px);
    const values = rows.flatMap((row) => {
      if (row.values.length === 0) return [];
      let best = row.values[0]!;
      let bestDistance = Infinity;
      for (const point of row.values) {
        const distance = Math.abs(point[0] - sigma);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = point;
        }
      }
      return [{ axisId: row.axis.axisId, value: best[1], unit: row.axis.limits.unit, tone: row.tone, y: row.projection.y(best[1]) }];
    });
    setHover(values.length ? { px, sigma, values } : null);
  };

  const plotBottom = TOP + ROW_HEIGHT * rows.length;

  return (
    <figure className="f2-axis-plot ax-chart" role="img" aria-label="选定连续分支的五轴坐标随路径进度变化">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${height}`}
        onPointerMove={handleMove}
        onPointerLeave={() => setHover(null)}
      >
        {SIGMA_TICKS.map((sigma) => {
          const x = xProjection.x(sigma);
          return (
            <g key={sigma}>
              <line className="ax-chart-grid" x1={x} x2={x} y1={TOP - 4} y2={plotBottom - 4} />
              <text className="ax-chart-tick" x={x} y={height - 10} textAnchor="middle">σ {formatTick(sigma)}</text>
            </g>
          );
        })}
        {rows.map(({ axis, values, color, tone, index, projection, baseline, rangeLow, rangeHigh }) => (
          <g key={axis.axisId}>
            {index > 0 && <line className="ax-chart-grid" x1={LEFT} x2={WIDTH - RIGHT} y1={TOP + index * ROW_HEIGHT} y2={TOP + index * ROW_HEIGHT} />}
            <line className="ax-chart-grid" x1={LEFT} x2={WIDTH - RIGHT} y1={baseline} y2={baseline} strokeDasharray="2 5" />
            <text x="10" y={baseline + 4} fill={color}>{axis.axisId}</text>
            <text className="ax-chart-tick" x={WIDTH - RIGHT} y={baseline - 8} textAnchor="end">
              {formatTick(rangeLow)} → {formatTick(rangeHigh)} {axis.limits.unit}
            </text>
            <g className={`ax-chart-series ax-tone-${tone}`}>
              <path d={pathFrom(values, projection)} />
            </g>
          </g>
        ))}
        {hover && (
          <g className="ax-chart-crosshair" pointerEvents="none">
            <line x1={hover.px} x2={hover.px} y1={TOP - 4} y2={plotBottom - 4} />
            {hover.values.map((value) => (
              <circle key={value.axisId} className={`ax-tone-${value.tone}`} cx={hover.px} cy={value.y} r={3} />
            ))}
          </g>
        )}
      </svg>
      {hover && (
        <div className="ax-chart-tooltip" style={{ left: `${(hover.px / WIDTH) * 100}%`, top: "14px" }}>
          <strong>σ {formatTick(hover.sigma)}</strong>
          {hover.values.map((value) => (
            <span key={value.axisId} className={`ax-tooltip-${value.tone}`}>
              {value.axisId}: {formatTick(value.value)} {value.unit}
            </span>
          ))}
        </div>
      )}
      <figcaption className="ax-chart-caption">local-power@1 · selected continuous branch · unwrapped coordinates</figcaption>
    </figure>
  );
}
