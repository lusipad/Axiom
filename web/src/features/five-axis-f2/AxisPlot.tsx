import type { JointPolynomialSegment, MachineAxis } from "./types";

const COLORS = ["#68d5ff", "#8ce6a4", "#f4c76b", "#ff8f70", "#c7a4ff"];

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
  const series = axes.map((axis, index) => ({ axis, values: samples(segments, index), color: COLORS[index] ?? "#ffffff" }));
  const width = 720;
  const height = 330;
  const left = 54;
  const right = 22;
  const top = 20;
  const rowHeight = 54;

  return (
    <figure className="f2-axis-plot" role="img" aria-label="选定连续分支的五轴坐标随路径进度变化">
      <svg viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id="f2-grid-fade" x1="0" x2="1">
            <stop offset="0" stopColor="#486075" stopOpacity=".55" />
            <stop offset="1" stopColor="#486075" stopOpacity=".08" />
          </linearGradient>
        </defs>
        {series.map(({ axis, values, color }, row) => {
          const numbers = values.map(([, value]) => value);
          const min = Math.min(...numbers);
          const max = Math.max(...numbers);
          const span = max - min || 1;
          const baseline = top + row * rowHeight + rowHeight / 2;
          const path = values.map(([sigma, value], index) => {
            const x = left + sigma * (width - left - right);
            const y = baseline + 17 - ((value - min) / span) * 34;
            return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
          }).join(" ");
          return (
            <g key={axis.axisId}>
              <line x1={left} x2={width - right} y1={baseline} y2={baseline} stroke="url(#f2-grid-fade)" />
              <text x="10" y={baseline + 4} fill={color}>{axis.axisId}</text>
              <text x={width - right} y={baseline - 8} textAnchor="end" className="axis-range">
                {min.toFixed(3)} → {max.toFixed(3)} {axis.limits.unit}
              </text>
              <path d={path} fill="none" stroke={color} strokeWidth="2.3" strokeLinecap="round" />
            </g>
          );
        })}
        {[0, 0.25, 0.5, 0.75, 1].map((sigma) => {
          const x = left + sigma * (width - left - right);
          return (
            <g key={sigma}>
              <line x1={x} x2={x} y1={top - 4} y2={top + rowHeight * 5 - 4} stroke="#7590a6" strokeOpacity=".14" />
              <text x={x} y={height - 10} textAnchor="middle" className="sigma-label">σ {sigma.toFixed(2)}</text>
            </g>
          );
        })}
      </svg>
      <figcaption>local-power@1 · selected continuous branch · unwrapped coordinates</figcaption>
    </figure>
  );
}
