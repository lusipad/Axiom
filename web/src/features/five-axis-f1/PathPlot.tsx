import type { AxisAlignedBoundingBox, M1ReferencePath, M2CandidateTaskGeometry, PositionSegment, Vector3 } from "./types";

interface PlotPoint {
  x: number;
  y: number;
}

interface PlotSeries {
  id: string;
  points: Vector3[];
}

interface Projector {
  point(value: Vector3): PlotPoint;
  width(value: number): number;
  height(value: number): number;
}

function segmentPoints(segment: PositionSegment): Vector3[] {
  if (segment.startPoint && segment.endPoint) return [segment.startPoint, segment.endPoint];
  if (segment.controlPoints?.length) return segment.controlPoints;
  return [];
}

function pathSeries(id: string, segments: PositionSegment[], staticPosition?: Vector3): PlotSeries {
  const points = segments.flatMap((segment, index) => {
    const values = segmentPoints(segment);
    return index === 0 ? values : values.slice(1);
  });
  return { id, points: points.length ? points : staticPosition ? [staticPosition] : [] };
}

function boundsPoints(box: AxisAlignedBoundingBox): Vector3[] {
  const [minX, minY, minZ] = box.minCorner;
  const [maxX, maxY, maxZ] = box.maxCorner;
  return [
    [minX, minY, minZ],
    [maxX, minY, minZ],
    [maxX, maxY, maxZ],
    [minX, maxY, maxZ],
  ];
}

function makeProjector(points: Vector3[]): Projector {
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const minX = Math.min(...xs, 0);
  const maxX = Math.max(...xs, 1);
  const minY = Math.min(...ys, 0);
  const maxY = Math.max(...ys, 1);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const scale = Math.min(540 / spanX, 270 / spanY);
  const width = spanX * scale;
  const height = spanY * scale;
  const left = 50 + (540 - width) / 2;
  const top = 34 + (270 - height) / 2;
  return {
    point: ([x, y]) => ({ x: left + (x - minX) * scale, y: top + height - (y - minY) * scale }),
    width: (value) => value * scale,
    height: (value) => value * scale,
  };
}

function pathData(points: Vector3[], projector: Projector): string {
  return points.map((point, index) => {
    const projected = projector.point(point);
    return `${index ? "L" : "M"}${projected.x.toFixed(2)} ${projected.y.toFixed(2)}`;
  }).join(" ");
}

export function PathPlot({
  reference,
  candidate,
}: {
  reference: M1ReferencePath;
  candidate: M2CandidateTaskGeometry;
}) {
  const referenceSeries = pathSeries("reference", reference.positionSegments, reference.staticPosition);
  const candidateSeries = pathSeries("candidate", candidate.positionSegments, candidate.staticPosition);
  const boxes = candidate.collisionContext?.stockFixtures ?? [];
  const allPoints = [
    ...referenceSeries.points,
    ...candidateSeries.points,
    ...boxes.flatMap((item) => boundsPoints(item.aabb)),
  ];
  const projector = makeProjector(allPoints);

  return (
    <div className="f1-plot-stage">
      <svg viewBox="0 0 640 340" role="img" aria-label="参考路径、候选路径与碰撞上下文的 XY 投影">
        <defs>
          <pattern id="f1-grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M 32 0 L 0 0 0 32" className="minor-grid" fill="none" />
          </pattern>
        </defs>
        <rect width="640" height="340" fill="url(#f1-grid)" />
        {boxes.map((item) => {
          const origin = projector.point([item.aabb.minCorner[0], item.aabb.maxCorner[1], item.aabb.minCorner[2]]);
          const width = projector.width(item.aabb.maxCorner[0] - item.aabb.minCorner[0]);
          const height = projector.height(item.aabb.maxCorner[1] - item.aabb.minCorner[1]);
          return (
            <g key={item.stockFixtureId} className={`f1-obstacle f1-obstacle-${item.category}`}>
              <rect x={origin.x} y={origin.y} width={Math.max(width, 1)} height={Math.max(height, 1)} />
              <text x={origin.x + 5} y={origin.y + 13}>{item.stockFixtureId}</text>
            </g>
          );
        })}
        <path className="f1-reference-path" d={pathData(referenceSeries.points, projector)} />
        <path className="f1-candidate-path" d={pathData(candidateSeries.points, projector)} />
        {referenceSeries.points.map((point, index) => {
          const projected = projector.point(point);
          return <circle key={`reference-${index}`} className="f1-reference-node" cx={projected.x} cy={projected.y} r="3" />;
        })}
        {candidateSeries.points.map((point, index) => {
          const projected = projector.point(point);
          return <circle key={`candidate-${index}`} className="f1-candidate-node" cx={projected.x} cy={projected.y} r="4" />;
        })}
        <text x="602" y="324" className="axis-label">X</text>
        <text x="28" y="30" className="axis-label">Y</text>
      </svg>
      <div className="f1-plot-legend" aria-label="图例">
        <span><i className="reference" />M1 reference</span>
        <span><i className="candidate" />M2 candidate</span>
        <span><i className="stock" />stock</span>
        <span><i className="fixture" />fixture</span>
      </div>
      <code className="f1-projection-label">XY projection · {candidate.positionSegments.length} continuous segment(s)</code>
    </div>
  );
}
