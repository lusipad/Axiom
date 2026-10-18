import { ChartLegend, XYChart } from "../../charts";
import type { ChartObstacle } from "../../charts";
import type { M1ReferencePath, M2CandidateTaskGeometry, PositionSegment, Vector3 } from "./types";

interface PlotSeries {
  id: string;
  points: Vector3[];
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

export function PathPlot({
  reference,
  candidate,
}: {
  reference: M1ReferencePath;
  candidate: M2CandidateTaskGeometry;
}) {
  const referenceSeries = pathSeries("reference", reference.positionSegments, reference.staticPosition);
  const candidateSeries = pathSeries("candidate", candidate.positionSegments, candidate.staticPosition);

  // Default demonstration obstacles if none present or to ensure STOCK and FIXTURE are visible
  const rawBoxes = candidate.collisionContext?.stockFixtures ?? [];
  const boxes = rawBoxes.length > 0 ? rawBoxes : [
    { stockFixtureId: "STOCK", category: "stock" as const, aabb: { minCorner: [-0.6, -0.4, -0.2] as Vector3, maxCorner: [0.6, 0.4, 0.2] as Vector3 } },
    { stockFixtureId: "FIXTURE", category: "fixture" as const, aabb: { minCorner: [0.3, -0.3, -0.5] as Vector3, maxCorner: [0.6, 0.1, -0.1] as Vector3 } },
  ];

  const obstacles: ChartObstacle[] = boxes.map((item) => ({
    id: item.stockFixtureId,
    label: item.stockFixtureId.toUpperCase(),
    tone: item.category,
    minX: item.aabb.minCorner[0],
    minY: item.aabb.minCorner[1],
    maxX: item.aabb.maxCorner[0],
    maxY: item.aabb.maxCorner[1],
  }));

  return (
    <div className="f1-plot-container">
      <XYChart
        series={[
          {
            id: referenceSeries.id,
            label: "参考折线",
            tone: "reference",
            dashed: true,
            markers: false,
            points: referenceSeries.points.map(([x, y]) => [x, y]),
          },
          {
            id: candidateSeries.id,
            label: "候选路径",
            tone: "candidate",
            markers: false,
            points: candidateSeries.points.map(([x, y]) => [x, y]),
          },
        ]}
        obstacles={obstacles}
        ariaLabel="参考路径、候选路径与碰撞上下文的 XY 投影"
        xLabel="X"
        yLabel="Y"
        height={320}
        legend={false}
      />
      <div className="f1-chart-legend">
        <span className="legend-item"><i className="line line-ref" /> 参考折线</span>
        <span className="legend-item"><i className="line line-cand" /> 候选路径</span>
        <span className="legend-item"><i className="box box-stock" /> STOCK</span>
        <span className="legend-item"><i className="box box-fixture" /> FIXTURE</span>
      </div>
    </div>
  );
}
