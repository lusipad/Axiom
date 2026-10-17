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
  const boxes = candidate.collisionContext?.stockFixtures ?? [];
  const obstacles: ChartObstacle[] = boxes.map((item) => ({
    id: item.stockFixtureId,
    label: item.stockFixtureId,
    tone: item.category,
    minX: item.aabb.minCorner[0],
    minY: item.aabb.minCorner[1],
    maxX: item.aabb.maxCorner[0],
    maxY: item.aabb.maxCorner[1],
  }));

  return (
    <>
      <XYChart
        series={[
          {
            id: referenceSeries.id,
            label: "M1 reference",
            tone: "reference",
            dashed: true,
            points: referenceSeries.points.map(([x, y]) => [x, y]),
          },
          {
            id: candidateSeries.id,
            label: "M2 candidate",
            tone: "candidate",
            points: candidateSeries.points.map(([x, y]) => [x, y]),
          },
        ]}
        obstacles={obstacles}
        ariaLabel="参考路径、候选路径与碰撞上下文的 XY 投影"
        xLabel="X"
        yLabel="Y"
        height={340}
        legend={false}
        caption={`XY projection · ${candidate.positionSegments.length} continuous segment(s)`}
      />
      <ChartLegend
        items={[
          { id: "reference", label: "M1 reference", tone: "reference", dashed: true },
          { id: "candidate", label: "M2 candidate", tone: "candidate" },
          { id: "stock", label: "stock", tone: "stock" },
          { id: "fixture", label: "fixture", tone: "fixture" },
        ]}
      />
    </>
  );
}
