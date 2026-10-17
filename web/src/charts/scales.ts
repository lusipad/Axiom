export type Vec2 = [number, number];

export function extent(values: number[]): [number, number] {
  let min = Infinity;
  let max = -Infinity;
  for (const value of values) {
    if (value < min) min = value;
    if (value > max) max = value;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  return [min, max];
}

export function formatTick(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 10000 || (abs > 0 && abs < 0.001)) return value.toExponential(1);
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 1) return String(Number(value.toFixed(2)));
  return String(Number(value.toFixed(3)));
}

export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!(max > min)) return [min];
  const span = max - min;
  const rawStep = span / Math.max(count - 1, 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const step = (residual >= 5 ? 10 : residual >= 2 ? 5 : residual >= 1 ? 2 : 1) * magnitude;
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let tick = start; tick <= max + step * 1e-9; tick += step) {
    ticks.push(Number(tick.toPrecision(12)));
  }
  return ticks.length ? ticks : [min, max];
}

export interface Projection {
  x(value: number): number;
  y(value: number): number;
  invertX(px: number): number;
  invertY(px: number): number;
  plotWidth: number;
  plotHeight: number;
  left: number;
  top: number;
  domainX: [number, number];
  domainY: [number, number];
}

export interface PlotBox {
  width: number;
  height: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export function makeProjection(
  domainX: [number, number],
  domainY: [number, number],
  box: PlotBox,
  equalAspect = false,
): Projection {
  const plotWidth = box.width - box.left - box.right;
  const plotHeight = box.height - box.top - box.bottom;
  const spanX = domainX[1] - domainX[0] || 1;
  const spanY = domainY[1] - domainY[0] || 1;
  let scaleX = plotWidth / spanX;
  let scaleY = plotHeight / spanY;
  let offsetX = 0;
  let offsetY = 0;
  if (equalAspect) {
    const scale = Math.min(scaleX, scaleY);
    offsetX = (plotWidth - spanX * scale) / 2;
    offsetY = (plotHeight - spanY * scale) / 2;
    scaleX = scale;
    scaleY = scale;
  }
  const left = box.left + offsetX;
  const top = box.top + offsetY;
  return {
    x: (value) => left + (value - domainX[0]) * scaleX,
    y: (value) => top + (domainY[1] - domainY[0] - (value - domainY[0])) * scaleY,
    invertX: (px) => domainX[0] + (px - left) / scaleX,
    invertY: (py) => domainY[1] - (py - top) / scaleY,
    plotWidth: spanX * scaleX,
    plotHeight: spanY * scaleY,
    left,
    top,
    domainX,
    domainY,
  };
}

export function pathFrom(points: Vec2[], projection: Projection): string {
  return points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${projection.x(x).toFixed(2)} ${projection.y(y).toFixed(2)}`)
    .join(" ");
}

export function nearestPointIndex(points: Vec2[], x: number, y: number, projection: Projection): number {
  let best = -1;
  let bestDistance = Infinity;
  points.forEach(([px, py], index) => {
    const dx = projection.x(px) - x;
    const dy = projection.y(py) - y;
    const distance = dx * dx + dy * dy;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  });
  return best;
}
