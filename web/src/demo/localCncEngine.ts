/**
 * Pure-TypeScript in-browser CNC trajectory evaluation, A/B comparison, and
 * single-cut white-box parameter diagnosis engine for static GitHub Pages (`github.io`)
 * deployments (`VITE_DEMO=1`).
 */

type Vec3 = [number, number, number];

const ZERO_VEC3: Vec3 = [0, 0, 0];

interface RawArc {
  segmentIndex: number;
  centerMm: [number, number];
  direction: "cw" | "ccw";
}

interface RawAxisLimit {
  axis: string;
  minimumPositionMm: number;
  maximumPositionMm: number;
  maximumVelocityMmS: number;
  maximumAccelerationMmS2: number;
  maximumJerkMmS3: number;
}

interface RawComparisonTolerances {
  durationSeconds?: number;
  pathDeviationMm?: number;
  pathDeviationRmsMm?: number | null;
  pathDeviationP99Mm?: number | null;
  jerkMmS3?: number | null;
  computationSeconds?: number;
}

interface RawBenchmarkCase {
  caseId: string;
  coordinateFrame?: string;
  unit?: string;
  samplePeriodSeconds: number;
  programmedFeedMmMin?: number | null;
  referencePath: number[][];
  referenceArcs?: RawArc[];
  axisLimits?: RawAxisLimit[];
  maximumPathDeviationMm: number;
  maximumEndpointErrorMm?: number;
  comparisonTolerances?: RawComparisonTolerances;
}

interface RawSample {
  sampleIndex: number;
  t: number;
  positionMm: number[];
  actualPositionMm?: number[] | null;
}

interface RawComputation {
  elapsedSeconds: number;
  environmentId?: string;
  method?: string;
}

interface RawAlgorithmExport {
  algorithmId: string;
  algorithmVersion: string;
  sourceKind?: string;
  caseContentHash?: string;
  coordinateFrame?: string;
  unit?: string;
  samplePeriodSeconds?: number;
  computation?: RawComputation | null;
  parameters?: Record<string, number> | null;
  samples: RawSample[];
}

export interface ProfileRegistryParam {
  parameterId: string;
  displayName: string;
  group: string;
  unit: string;
  valueType: string;
  bounds: [number, number];
  defaultValue: number;
  axisScope: string;
  description: string;
}

export interface ProfileParameterBinding {
  vendorParameterId: string;
  canonicalTargets: string[];
  transform: string;
  scale: number;
  offset: number;
  tunability: "nc-tunable" | "drive-side" | "read-only";
}

export interface ControllerProfileSpec {
  profileId: string;
  vendorName: string;
  controllerFamily: string;
  registry: {
    registryId: string;
    parameters: ProfileRegistryParam[];
  };
  capabilities: Record<string, boolean>;
  bindings: ProfileParameterBinding[];
  profileContentHash?: string;
}

interface MetricLocation {
  sampleIndex: number;
  t: number;
  axis?: string;
  referenceSegmentIndex?: number;
}

interface MetricEntry {
  value: number | null;
  unit: string;
  location?: MetricLocation;
}

function deterministicHash(input: unknown): string {
  const str = JSON.stringify(input) ?? "";
  let h1 = 0xdeadbeef ^ str.length;
  let h2 = 0x41c6ce57 ^ str.length;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 =
    Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^
    Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 =
    Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^
    Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  const hex1 = (h1 >>> 0).toString(16).padStart(8, "0");
  const hex2 = (h2 >>> 0).toString(16).padStart(8, "0");
  return `${hex1}${hex2}${hex1}${hex2}${hex1}${hex2}${hex1}${hex2}`;
}

function toVec3(p: number[] | null | undefined): Vec3 {
  if (!Array.isArray(p) || p.length < 2) return [0, 0, 0];
  return [Number(p[0] ?? 0) || 0, Number(p[1] ?? 0) || 0, Number(p[2] ?? 0) || 0];
}

function dist3(a: Vec3, b: Vec3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

function posMod(x: number, m: number): number {
  return ((x % m) + m) % m;
}

function arcGeometry(
  path: Vec3[],
  arc: RawArc,
): { center: [number, number]; radius: number; a0: number; sweep: number } {
  const start = path[arc.segmentIndex] ?? ZERO_VEC3;
  const end = path[arc.segmentIndex + 1] ?? start;
  const cx = Number(arc.centerMm[0]) || 0;
  const cy = Number(arc.centerMm[1]) || 0;
  const a0 = Math.atan2(start[1] - cy, start[0] - cx);
  const a1 = Math.atan2(end[1] - cy, end[0] - cx);
  const twoPi = 2 * Math.PI;
  let rawSweep =
    arc.direction === "ccw"
      ? posMod(a1 - a0, twoPi)
      : -posMod(a0 - a1, twoPi);
  if (Math.abs(rawSweep) < 1e-9) {
    rawSweep = arc.direction === "ccw" ? twoPi : -twoPi;
  }
  const radius = Math.hypot(start[0] - cx, start[1] - cy);
  return { center: [cx, cy], radius, a0, sweep: rawSweep };
}

function pointToSegmentDistance(
  pt: Vec3,
  segIndex: number,
  path: Vec3[],
  arcsBySeg: Map<number, RawArc>,
): number {
  const p0 = path[segIndex] ?? ZERO_VEC3;
  const p1 = path[segIndex + 1] ?? p0;
  const arc = arcsBySeg.get(segIndex);
  if (arc) {
    const { center, radius, a0, sweep } = arcGeometry(path, arc);
    const rx = pt[0] - center[0];
    const ry = pt[1] - center[1];
    const radial = Math.hypot(rx, ry);
    const sign = sweep >= 0 ? 1 : -1;
    const offset = posMod((Math.atan2(ry, rx) - a0) * sign, 2 * Math.PI);
    const dz = pt[2] - p0[2];
    if (offset <= Math.abs(sweep) + 1e-7 || radial === 0) {
      return Math.hypot(radial - radius, dz);
    }
    return Math.min(dist3(pt, p0), dist3(pt, p1));
  }
  const vx = p1[0] - p0[0];
  const vy = p1[1] - p0[1];
  const vz = p1[2] - p0[2];
  const lenSq = vx * vx + vy * vy + vz * vz;
  if (lenSq <= 1e-18) return dist3(pt, p0);
  const u = Math.max(
    0,
    Math.min(
      1,
      ((pt[0] - p0[0]) * vx + (pt[1] - p0[1]) * vy + (pt[2] - p0[2]) * vz) /
        lenSq,
    ),
  );
  return Math.hypot(
    pt[0] - (p0[0] + u * vx),
    pt[1] - (p0[1] + u * vy),
    pt[2] - (p0[2] + u * vz),
  );
}

function computePathDeviations(
  positions: Vec3[],
  path: Vec3[],
  arcs: RawArc[] = [],
): { errors: number[]; nearestSegments: number[] } {
  const arcsBySeg = new Map<number, RawArc>();
  for (const arc of arcs) {
    arcsBySeg.set(Number(arc.segmentIndex), arc);
  }
  const nSegs = Math.max(1, path.length - 1);
  const errors: number[] = new Array<number>(positions.length);
  const nearestSegments: number[] = new Array<number>(positions.length);
  for (let i = 0; i < positions.length; i++) {
    const pt = positions[i] ?? ZERO_VEC3;
    let bestErr = Infinity;
    let bestSeg = 0;
    for (let s = 0; s < nSegs; s++) {
      const d = pointToSegmentDistance(pt, s, path, arcsBySeg);
      if (d < bestErr) {
        bestErr = d;
        bestSeg = s;
      }
    }
    errors[i] = bestErr;
    nearestSegments[i] = bestSeg;
  }
  return { errors, nearestSegments };
}

function quantile(values: number[], q: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  const baseVal = sorted[base] ?? 0;
  const nextVal = sorted[Math.min(sorted.length - 1, base + 1)] ?? baseVal;
  return baseVal + rest * (nextVal - baseVal);
}

function rms(values: number[]): number {
  if (values.length === 0) return 0;
  let sumSq = 0;
  for (const v of values) sumSq += v * v;
  return Math.sqrt(sumSq / values.length);
}

function referencePathLengthMm(
  path: Vec3[],
  arcs: RawArc[] = [],
): number {
  const arcsBySeg = new Map<number, RawArc>();
  for (const a of arcs) arcsBySeg.set(a.segmentIndex, a);
  let total = 0;
  for (let i = 0; i < path.length - 1; i++) {
    const arc = arcsBySeg.get(i);
    if (arc) {
      const { radius, sweep } = arcGeometry(path, arc);
      total += radius * Math.abs(sweep);
    } else {
      total += dist3(path[i] ?? ZERO_VEC3, path[i + 1] ?? ZERO_VEC3);
    }
  }
  return total;
}

function findReferenceCorners(
  path: Vec3[],
  arcs: RawArc[] = [],
): Array<{ vertexIndex: number; angleDeg: number }> {
  const arcsBySeg = new Map<number, RawArc>();
  for (const a of arcs) arcsBySeg.set(a.segmentIndex, a);
  const ends: Array<{ index: number; startTan: Vec3; endTan: Vec3 }> = [];
  for (let i = 0; i < path.length - 1; i++) {
    const arc = arcsBySeg.get(i);
    if (arc) {
      const { a0, sweep } = arcGeometry(path, arc);
      const sign = sweep >= 0 ? 1 : -1;
      const t0: Vec3 = [-Math.sin(a0) * sign, Math.cos(a0) * sign, 0];
      const t1: Vec3 = [
        -Math.sin(a0 + sweep) * sign,
        Math.cos(a0 + sweep) * sign,
        0,
      ];
      ends.push({ index: i, startTan: t0, endTan: t1 });
    } else {
      const p0 = path[i] ?? ZERO_VEC3;
      const p1 = path[i + 1] ?? p0;
      const dx = p1[0] - p0[0];
      const dy = p1[1] - p0[1];
      const dz = p1[2] - p0[2];
      const len = Math.hypot(dx, dy, dz);
      if (len > 1e-9) {
        const u: Vec3 = [dx / len, dy / len, dz / len];
        ends.push({ index: i, startTan: u, endTan: u });
      }
    }
  }
  const corners: Array<{ vertexIndex: number; angleDeg: number }> = [];
  for (let i = 0; i < ends.length - 1; i++) {
    const cur = ends[i];
    const nxt = ends[i + 1];
    if (!cur || !nxt) continue;
    const b = cur.endTan;
    const a = nxt.startTan;
    const dot = Math.max(-1, Math.min(1, b[0] * a[0] + b[1] * a[1] + b[2] * a[2]));
    const deg = (Math.acos(dot) * 180) / Math.PI;
    if (deg >= 15) {
      corners.push({ vertexIndex: nxt.index, angleDeg: deg });
    }
  }
  return corners;
}

function normalizeCase(raw: unknown): RawBenchmarkCase {
  if (!raw || typeof raw !== "object") {
    throw new Error("无效的基准案例 JSON：缺少 case 对象");
  }
  const obj = raw as Record<string, unknown>;
  const refPath = Array.isArray(obj.referencePath) ? obj.referencePath : [];
  if (refPath.length < 2) {
    throw new Error("无效的基准案例 JSON：referencePath 至少需要 2 个路径点");
  }
  const samplePeriod = Number(obj.samplePeriodSeconds);
  if (!Number.isFinite(samplePeriod) || samplePeriod <= 0) {
    throw new Error("无效的基准案例 JSON：samplePeriodSeconds 必须为正数");
  }
  const defaultAxes: RawAxisLimit[] = ["X", "Y", "Z"].map((axis) => ({
    axis,
    minimumPositionMm: -1000,
    maximumPositionMm: 1000,
    maximumVelocityMmS: 500,
    maximumAccelerationMmS2: 20000,
    maximumJerkMmS3: 2000000,
  }));
  return {
    caseId: String(obj.caseId ?? "custom.case"),
    coordinateFrame: String(obj.coordinateFrame ?? "workpiece"),
    unit: String(obj.unit ?? "mm"),
    samplePeriodSeconds: samplePeriod,
    programmedFeedMmMin:
      obj.programmedFeedMmMin != null ? Number(obj.programmedFeedMmMin) : null,
    referencePath: refPath as number[][],
    referenceArcs: Array.isArray(obj.referenceArcs)
      ? (obj.referenceArcs as RawArc[])
      : [],
    axisLimits:
      Array.isArray(obj.axisLimits) && obj.axisLimits.length > 0
        ? (obj.axisLimits as RawAxisLimit[])
        : defaultAxes,
    maximumPathDeviationMm: Number(obj.maximumPathDeviationMm ?? 0.05),
    maximumEndpointErrorMm: Number(obj.maximumEndpointErrorMm ?? 0.005),
    comparisonTolerances: (obj.comparisonTolerances ?? {}) as RawComparisonTolerances,
  };
}

function normalizeExport(raw: unknown, label = "export"): RawAlgorithmExport {
  if (!raw || typeof raw !== "object") {
    throw new Error(`无效的轨迹 JSON（${label}）：缺少对象结构`);
  }
  const obj = raw as Record<string, unknown>;
  const samples = Array.isArray(obj.samples) ? (obj.samples as RawSample[]) : [];
  if (samples.length < 2) {
    throw new Error(`无效的轨迹 JSON（${label}）：samples 至少需要 2 个采样点`);
  }
  return {
    algorithmId: String(obj.algorithmId ?? "custom.export"),
    algorithmVersion: String(obj.algorithmVersion ?? "v1"),
    sourceKind: String(obj.sourceKind ?? "algorithm-export"),
    caseContentHash:
      typeof obj.caseContentHash === "string" ? obj.caseContentHash : undefined,
    coordinateFrame:
      typeof obj.coordinateFrame === "string" ? obj.coordinateFrame : undefined,
    unit: typeof obj.unit === "string" ? obj.unit : undefined,
    samplePeriodSeconds:
      obj.samplePeriodSeconds != null
        ? Number(obj.samplePeriodSeconds)
        : undefined,
    computation: (obj.computation as RawComputation | null | undefined) ?? null,
    parameters:
      obj.parameters && typeof obj.parameters === "object"
        ? (obj.parameters as Record<string, number>)
        : null,
    samples,
  };
}

function analyseRun(caseObj: RawBenchmarkCase, run: RawAlgorithmExport) {
  const positions = run.samples.map((s) => toVec3(s.positionMm));
  const times = run.samples.map((s, idx) =>
    Number.isFinite(Number(s.t))
      ? Number(s.t)
      : idx * caseObj.samplePeriodSeconds,
  );
  const path = caseObj.referencePath.map((p) => toVec3(p));
  const arcs = caseObj.referenceArcs ?? [];
  const { errors, nearestSegments } = computePathDeviations(
    positions,
    path,
    arcs,
  );

  const makeLoc = (
    sampleIndex: number,
    axis: string | null = null,
    referenceSegmentIndex: number | null = null,
  ): MetricLocation => ({
    sampleIndex,
    t: Number(times[sampleIndex] ?? sampleIndex * caseObj.samplePeriodSeconds),
    ...(axis ? { axis } : {}),
    ...(referenceSegmentIndex != null ? { referenceSegmentIndex } : {}),
  });

  let maxErrIdx = 0;
  for (let i = 1; i < errors.length; i++) {
    if ((errors[i] ?? 0) > (errors[maxErrIdx] ?? 0)) maxErrIdx = i;
  }

  const sampledPathDevMetric: MetricEntry = {
    value: errors[maxErrIdx] ?? 0,
    unit: "mm",
    location: makeLoc(maxErrIdx, null, nearestSegments[maxErrIdx] ?? 0),
  };

  const corners = findReferenceCorners(path, arcs);
  let cornerSpeedMetric: MetricEntry = { value: null, unit: "mm/s" };
  for (const c of corners) {
    let nearest = 0;
    let bestD = Infinity;
    const cornerPt = path[c.vertexIndex] ?? ZERO_VEC3;
    for (let i = 0; i < positions.length; i++) {
      const d = dist3(positions[i] ?? ZERO_VEC3, cornerPt);
      if (d < bestD) {
        bestD = d;
        nearest = i;
      }
    }
    const left = Math.max(0, nearest - 1);
    const right = Math.min(positions.length - 1, nearest + 1);
    if (right > left) {
      const spd =
        dist3(positions[right] ?? ZERO_VEC3, positions[left] ?? ZERO_VEC3) /
        ((right - left) * caseObj.samplePeriodSeconds);
      if (cornerSpeedMetric.value === null || spd < cornerSpeedMetric.value) {
        cornerSpeedMetric = {
          value: spd,
          unit: "mm/s",
          location: makeLoc(nearest, null, c.vertexIndex),
        };
      }
    }
  }

  const refLen = referencePathLengthMm(path, arcs);
  const dur = times[times.length - 1] ?? 0;

  const startErr = dist3(positions[0] ?? ZERO_VEC3, path[0] ?? ZERO_VEC3);
  const endErr = dist3(
    positions[positions.length - 1] ?? ZERO_VEC3,
    path[path.length - 1] ?? ZERO_VEC3,
  );
  const endIdx = startErr >= endErr ? 0 : positions.length - 1;
  const endpointMetric: MetricEntry = {
    value: Math.max(startErr, endErr),
    unit: "mm",
    location: makeLoc(endIdx),
  };

  const metrics: Record<string, MetricEntry> = {
    durationSeconds: { value: dur, unit: "s" },
    sampledPathDeviationMaxMm: sampledPathDevMetric,
    sampledPathDeviationRmsMm: { value: rms(errors), unit: "mm" },
    sampledPathDeviationP95Mm: { value: quantile(errors, 0.95), unit: "mm" },
    sampledPathDeviationP99Mm: { value: quantile(errors, 0.99), unit: "mm" },
    cornerSpeedMinMmS: cornerSpeedMetric,
    feedUtilization: {
      value:
        caseObj.programmedFeedMmMin && dur > 0
          ? refLen / ((dur * caseObj.programmedFeedMmMin) / 60)
          : null,
      unit: "ratio",
    },
    endpointErrorMaxMm: endpointMetric,
  };

  const checks: Array<{
    checkId: string;
    status: "WithinLimit" | "Violated" | "InsufficientSamples";
    value: number | null;
    limit: number;
    unit: string;
    location?: MetricLocation;
  }> = [];

  const addCheck = (checkId: string, metric: MetricEntry, limit: number) => {
    const status =
      metric.value === null
        ? "InsufficientSamples"
        : metric.value > limit
          ? "Violated"
          : "WithinLimit";
    checks.push({
      checkId,
      status,
      value: metric.value,
      limit,
      unit: metric.unit,
      ...(metric.location ? { location: metric.location } : {}),
    });
  };

  addCheck(
    "sampled-path-deviation",
    sampledPathDevMetric,
    caseObj.maximumPathDeviationMm,
  );
  addCheck(
    "endpoints",
    endpointMetric,
    caseObj.maximumEndpointErrorMm ?? 0.005,
  );

  const axisLimits = caseObj.axisLimits ?? [];
  for (let axIdx = 0; axIdx < axisLimits.length; axIdx++) {
    const lim = axisLimits[axIdx];
    if (!lim) continue;
    let worstExcess = 0;
    let worstIdx = 0;
    for (let i = 0; i < positions.length; i++) {
      const pt = positions[i] ?? ZERO_VEC3;
      const v = pt[axIdx as 0 | 1 | 2] ?? 0;
      const ex = Math.max(
        lim.minimumPositionMm - v,
        v - lim.maximumPositionMm,
      );
      if (i === 0 || ex > worstExcess) {
        worstExcess = ex;
        worstIdx = i;
      }
    }
    addCheck(
      `${lim.axis}.position-range`,
      {
        value: Math.max(0, worstExcess),
        unit: "mm",
        location: makeLoc(worstIdx, lim.axis),
      },
      0,
    );
  }

  let diffs: Vec3[] = positions;
  const orders: Array<{
    name: "Velocity" | "Acceleration" | "Jerk";
    unit: string;
    field:
      | "maximumVelocityMmS"
      | "maximumAccelerationMmS2"
      | "maximumJerkMmS3";
  }> = [
    { name: "Velocity", unit: "mm/s", field: "maximumVelocityMmS" },
    {
      name: "Acceleration",
      unit: "mm/s^2",
      field: "maximumAccelerationMmS2",
    },
    { name: "Jerk", unit: "mm/s^3", field: "maximumJerkMmS3" },
  ];

  for (let order = 1; order <= orders.length; order++) {
    const spec = orders[order - 1];
    if (!spec) continue;
    const nextDiffs: Vec3[] = [];
    for (let i = 0; i < diffs.length - 1; i++) {
      const d0 = diffs[i] ?? ZERO_VEC3;
      const d1 = diffs[i + 1] ?? ZERO_VEC3;
      nextDiffs.push([
        (d1[0] - d0[0]) / caseObj.samplePeriodSeconds,
        (d1[1] - d0[1]) / caseObj.samplePeriodSeconds,
        (d1[2] - d0[2]) / caseObj.samplePeriodSeconds,
      ]);
    }
    diffs = nextDiffs;

    let globalMetric: MetricEntry = { value: null, unit: spec.unit };

    for (let axIdx = 0; axIdx < axisLimits.length; axIdx++) {
      const lim = axisLimits[axIdx];
      if (!lim) continue;
      let axisMetric: MetricEntry = { value: null, unit: spec.unit };
      if (diffs.length > 0) {
        let bestIdx = 0;
        const firstD = diffs[0] ?? ZERO_VEC3;
        let bestVal = Math.abs(firstD[axIdx as 0 | 1 | 2] ?? 0);
        for (let i = 1; i < diffs.length; i++) {
          const curD = diffs[i] ?? ZERO_VEC3;
          const v = Math.abs(curD[axIdx as 0 | 1 | 2] ?? 0);
          if (v > bestVal) {
            bestVal = v;
            bestIdx = i;
          }
        }
        axisMetric = {
          value: bestVal,
          unit: spec.unit,
          location: makeLoc(bestIdx + order, lim.axis),
        };
        if (globalMetric.value === null || bestVal > globalMetric.value) {
          globalMetric = axisMetric;
        }
      }
      addCheck(
        `${lim.axis}.discrete-${spec.name.toLowerCase()}`,
        axisMetric,
        lim[spec.field],
      );
    }
    metrics[`discrete${spec.name}Max`] = globalMetric;
  }

  const jerkMags = diffs.map((d) => Math.hypot(d[0], d[1], d[2]));
  metrics.discreteJerkRms = {
    value: jerkMags.length > 0 ? rms(jerkMags) : null,
    unit: "mm/s^3",
  };
  metrics.computationSeconds = {
    value:
      run.computation && Number.isFinite(Number(run.computation.elapsedSeconds))
        ? Number(run.computation.elapsedSeconds)
        : null,
    unit: "s",
  };

  return {
    algorithmId: run.algorithmId,
    algorithmVersion: run.algorithmVersion,
    sourceKind: run.sourceKind ?? "algorithm-export",
    exportContentHash: deterministicHash(run),
    sampleCount: run.samples.length,
    metrics,
    checks,
    _positions: positions,
    _times: times,
    _errors: errors,
    _nearestSegments: nearestSegments,
  };
}

/**
 * Pure-TypeScript evaluation for `POST /api/v1/benchmarks/cnc/compare`.
 */
export function compareCncExportsLocal(
  payload: unknown,
): Record<string, unknown> {
  if (!payload || typeof payload !== "object") {
    throw new Error("请求体格式错误：需要包含 case、baseline 和 candidate");
  }
  const req = payload as Record<string, unknown>;
  const caseObj = normalizeCase(req.case);
  const baselineRun = normalizeExport(req.baseline, "baseline");
  const candidateRun = normalizeExport(req.candidate, "candidate");

  if (
    baselineRun.caseContentHash &&
    candidateRun.caseContentHash &&
    baselineRun.caseContentHash !== candidateRun.caseContentHash
  ) {
    throw new Error(
      "基线 A 与候选 B 的 caseContentHash 不一致，无法在同一基准案例下对比",
    );
  }

  const baseAnalysis = analyseRun(caseObj, baselineRun);
  const candAnalysis = analyseRun(caseObj, candidateRun);

  const tol = caseObj.comparisonTolerances ?? {};
  const compared: Array<[string, number]> = [
    ["durationSeconds", Number(tol.durationSeconds ?? 1e-6)],
    ["sampledPathDeviationMaxMm", Number(tol.pathDeviationMm ?? 1e-6)],
  ];
  if (tol.pathDeviationRmsMm != null) {
    compared.push(["sampledPathDeviationRmsMm", Number(tol.pathDeviationRmsMm)]);
  }
  if (tol.pathDeviationP99Mm != null) {
    compared.push(["sampledPathDeviationP99Mm", Number(tol.pathDeviationP99Mm)]);
  }
  if (tol.jerkMmS3 != null) {
    compared.push(["discreteJerkMax", Number(tol.jerkMmS3)]);
  }
  compared.push(["computationSeconds", Number(tol.computationSeconds ?? 1e-4)]);

  const differences = compared.map(([metricId, tolerance]) => {
    const left = baseAnalysis.metrics[metricId] ?? { value: null, unit: "" };
    const right = candAnalysis.metrics[metricId] ?? { value: null, unit: "" };
    let reason: string | null = null;
    if (left.value === null || right.value === null) {
      reason = "Both exports must include this measurement";
    } else if (metricId === "computationSeconds") {
      const a = baselineRun.computation;
      const b = candidateRun.computation;
      if (
        !a ||
        !b ||
        a.environmentId !== b.environmentId ||
        a.method !== b.method
      ) {
        reason = "Timing environment and measurement method must match";
      }
    }
    const delta =
      reason === null && left.value !== null && right.value !== null
        ? right.value - left.value
        : null;
    const status =
      delta === null
        ? "NotComparable"
        : delta > tolerance
          ? "Regressed"
          : delta < -tolerance
            ? "Improved"
            : "WithinTolerance";
    return {
      metricId,
      baseline: left.value,
      candidate: right.value,
      delta,
      unit: left.unit,
      tolerance,
      status,
      ...(reason ? { reason } : {}),
    };
  });

  const reasons: string[] = [];
  let outcome:
    | "Improved"
    | "Regressed"
    | "Tradeoff"
    | "WithinTolerance"
    | "CandidateViolatesLimits"
    | "Inconclusive";

  const candViolated = candAnalysis.checks.some((c) => c.status === "Violated");
  const anyNonWithin = [
    ...baseAnalysis.checks,
    ...candAnalysis.checks,
  ].some((c) => c.status !== "WithinLimit");

  if (candViolated) {
    outcome = "CandidateViolatesLimits";
    reasons.push("Candidate violates one or more sampled-command limits");
  } else if (anyNonWithin) {
    outcome = "Inconclusive";
    reasons.push(
      "A/B quality comparison requires a valid baseline and enough samples for every requested check",
    );
  } else if (baseAnalysis.sourceKind !== candAnalysis.sourceKind) {
    outcome = "Inconclusive";
    reasons.push(
      "Synthetic examples and algorithm exports cannot establish one A/B result",
    );
  } else {
    const statuses = new Set(differences.map((d) => d.status));
    if (statuses.has("Improved") && statuses.has("Regressed")) {
      outcome = "Tradeoff";
    } else if (statuses.has("Regressed")) {
      outcome = "Regressed";
    } else if (statuses.has("Improved")) {
      outcome = "Improved";
    } else {
      outcome = "WithinTolerance";
    }
    reasons.push(
      "Lower duration, sampled path deviation and comparable reported computation time are preferred; no weighted score is used",
    );
  }
  reasons.push(
    "Discrete V/A/J differences do not certify continuous velocity, acceleration or jerk",
  );
  reasons.push(
    "Computation timing is producer-reported; a single observation does not establish statistical significance",
  );
  if (
    baseAnalysis.sourceKind === "synthetic-example" ||
    candAnalysis.sourceKind === "synthetic-example"
  ) {
    reasons.push(
      "Synthetic example data: this report is not evidence about a production algorithm",
    );
  }

  const stripInternal = (a: ReturnType<typeof analyseRun>) => ({
    algorithmId: a.algorithmId,
    algorithmVersion: a.algorithmVersion,
    sourceKind: a.sourceKind,
    exportContentHash: a.exportContentHash,
    sampleCount: a.sampleCount,
    metrics: a.metrics,
    checks: a.checks,
  });

  const reportWithoutHash = {
    schemaId: "axiom.cnc-benchmark-report@1",
    evaluatorVersion: "cnc-sampled-comparison@1",
    caseId: caseObj.caseId,
    caseContentHash: deterministicHash(caseObj),
    scope: "sampled-xyz-command",
    uncheckedProperties: [
      "inter-sample-continuous-trajectory",
      "actual-servo-following-error",
      "cutting-load-and-spindle-dynamics",
      "thermal-and-geometric-volumetric-error",
    ],
    baseline: stripInternal(baseAnalysis),
    candidate: stripInternal(candAnalysis),
    differences,
    outcome,
    reasons,
  };

  return {
    ...reportWithoutHash,
    reportContentHash: deterministicHash(reportWithoutHash),
  };
}

function extractResonanceSpectrum(
  signalCols: number[][],
  period: number,
): { freqHz: number; bandRmsMm: number } {
  const n = signalCols[0]?.length ?? 0;
  const fs = 1 / period;
  const nyquist = 0.5 * fs;
  const fLo = 45.0;
  if (n < 24 || nyquist <= fLo * 1.15) {
    return { freqHz: 0, bandRmsMm: 0 };
  }
  const fHi = Math.min(450.0, 0.9 * nyquist);

  const window = new Float64Array(n);
  let winSqSum = 0;
  for (let i = 0; i < n; i++) {
    const w = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / Math.max(1, n - 1));
    window[i] = w;
    winSqSum += w * w;
  }
  const winNorm = Math.sqrt(winSqSum / n) || 1;

  const detrendedCols = signalCols.map((col) => {
    let sum = 0;
    for (let i = 0; i < n; i++) sum += col[i] ?? 0;
    const mean = sum / n;
    const out = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      out[i] = ((col[i] ?? 0) - mean) * (window[i] ?? 0);
    }
    return out;
  });

  const maxK = Math.floor(n / 2);
  const freqs: number[] = [];
  const psdAmp: number[] = [];

  for (let k = 0; k <= maxK; k++) {
    const f = k / (n * period);
    freqs.push(f);
    if (f < fLo - 20 || f > fHi + 20) {
      psdAmp.push(0);
      continue;
    }
    let sqSum = 0;
    const omega = (-2 * Math.PI * k) / n;
    for (const col of detrendedCols) {
      let re = 0;
      let im = 0;
      for (let t = 0; t < n; t++) {
        const ang = omega * t;
        const val = col[t] ?? 0;
        re += val * Math.cos(ang);
        im += val * Math.sin(ang);
      }
      const amp = (Math.hypot(re, im) / (n * winNorm)) * Math.SQRT2;
      sqSum += amp * amp;
    }
    psdAmp.push(Math.sqrt(sqSum));
  }

  let bestWeighted = -1;
  let fDom = 0;
  for (let k = 0; k < freqs.length; k++) {
    const f = freqs[k] ?? 0;
    if (f < fLo || f > fHi) continue;
    const w = (psdAmp[k] ?? 0) * Math.min(f / 80.0, 2.5);
    if (w > bestWeighted) {
      bestWeighted = w;
      fDom = f;
    }
  }
  if (fDom <= 0) return { freqHz: 0, bandRmsMm: 0 };

  let bandSq = 0;
  for (let k = 0; k < freqs.length; k++) {
    const f = freqs[k] ?? 0;
    const amp = psdAmp[k] ?? 0;
    if (f >= Math.max(fLo, fDom - 15) && f <= Math.min(fHi, fDom + 15)) {
      bandSq += amp * amp;
    }
  }
  return { freqHz: fDom, bandRmsMm: Math.sqrt(bandSq) };
}

/**
 * Pure-TypeScript single-cut parameter diagnosis for `POST /api/v1/benchmarks/cnc/param-diagnose`.
 */
export function diagnoseSingleRunLocal(
  payload: unknown,
  controllerProfiles: ControllerProfileSpec[],
): Record<string, unknown> {
  if (!payload || typeof payload !== "object") {
    throw new Error("单刀快诊请求体无效：缺少 case 与 export");
  }
  const req = payload as Record<string, unknown>;
  const caseObj = normalizeCase(req.case);
  const runObj = normalizeExport(req.export, "export");
  const profileId = String(req.profileId ?? "siemens-sinumerik-840d@1");
  const includeDriveSide = req.includeDriveSide !== false;

  const prof =
    controllerProfiles.find((p) => p.profileId === profileId) ??
    controllerProfiles[0];
  if (!prof) {
    throw new Error(`未找到数控系统档案：${profileId}`);
  }

  const analysis = analyseRun(caseObj, runObj);
  const positions = analysis._positions;
  const cmdErrors = analysis._errors;
  const path = caseObj.referencePath.map((p) => toVec3(p));
  const arcs = caseObj.referenceArcs ?? [];

  const hasArcs = arcs.length > 0;
  const corners = findReferenceCorners(path, arcs);
  const hasCorners = corners.length > 0;
  let microSegCount = 0;
  for (let i = 0; i < path.length - 1; i++) {
    if (dist3(path[i] ?? ZERO_VEC3, path[i + 1] ?? ZERO_VEC3) <= 1.2) {
      microSegCount++;
    }
  }
  const hasMicroSegments = microSegCount >= 3;

  const firstSample = runObj.samples[0];
  const hasActual =
    Array.isArray(firstSample?.actualPositionMm) &&
    firstSample.actualPositionMm.length >= 2;
  const actPositions = hasActual
    ? runObj.samples.map((s) => toVec3(s.actualPositionMm ?? s.positionMm))
    : null;
  const actDeviations = actPositions
    ? computePathDeviations(actPositions, path, arcs).errors
    : null;

  const cmdVel: Vec3[] = [];
  for (let i = 0; i < positions.length - 1; i++) {
    const p0 = positions[i] ?? ZERO_VEC3;
    const p1 = positions[i + 1] ?? ZERO_VEC3;
    cmdVel.push([
      (p1[0] - p0[0]) / caseObj.samplePeriodSeconds,
      (p1[1] - p0[1]) / caseObj.samplePeriodSeconds,
      (p1[2] - p0[2]) / caseObj.samplePeriodSeconds,
    ]);
  }
  const reversalIndices: number[] = [];
  for (let i = 0; i < cmdVel.length - 1; i++) {
    const v0 = cmdVel[i] ?? ZERO_VEC3;
    const v1 = cmdVel[i + 1] ?? ZERO_VEC3;
    if (v0[0] * v1[0] <= 0 || v0[1] * v1[1] <= 0) {
      reversalIndices.push(i + 1);
    }
  }
  const hasXyReversals = reversalIndices.length > 0;

  let quadGlitchExcessMm = 0;
  let normalServoErrorMaxMm = 0;
  let dominantResonanceFreqHz = 0;
  let resonanceBandRmsMm = 0;

  if (actPositions && actDeviations) {
    const halfWin = Math.max(
      3,
      Math.min(25, Math.round(0.015 / caseObj.samplePeriodSeconds)),
    );
    for (const rIdx of reversalIndices) {
      const lo = Math.max(0, rIdx - halfWin);
      const hi = Math.min(actPositions.length - 1, rIdx + halfWin);
      for (let k = lo; k <= hi; k++) {
        const ex = Math.max(0, (actDeviations[k] ?? 0) - (cmdErrors[k] ?? 0));
        if (ex > quadGlitchExcessMm) quadGlitchExcessMm = ex;
      }
    }

    const normalCols: [number[], number[], number[]] = [[], [], []];
    for (let i = 0; i < positions.length; i++) {
      const v = cmdVel[Math.min(i, Math.max(0, cmdVel.length - 1))] ?? [
        1, 0, 0,
      ];
      const spd = Math.hypot(v[0], v[1], v[2]) || 1;
      const tx = v[0] / spd;
      const ty = v[1] / spd;
      const tz = v[2] / spd;
      const cp = positions[i] ?? ZERO_VEC3;
      const ap = actPositions[i] ?? ZERO_VEC3;
      const ex = cp[0] - ap[0];
      const ey = cp[1] - ap[1];
      const ez = cp[2] - ap[2];
      const tang = ex * tx + ey * ty + ez * tz;
      const nx = ex - tang * tx;
      const ny = ey - tang * ty;
      const nz = ez - tang * tz;
      const nNorm = Math.hypot(nx, ny, nz);
      if (nNorm > normalServoErrorMaxMm) normalServoErrorMaxMm = nNorm;
      normalCols[0].push(nx);
      normalCols[1].push(ny);
      normalCols[2].push(nz);
    }

    const resSpec = extractResonanceSpectrum(
      normalCols,
      caseObj.samplePeriodSeconds,
    );
    dominantResonanceFreqHz = resSpec.freqHz;
    resonanceBandRmsMm = resSpec.bandRmsMm;
  }

  const paramSpecs = new Map<string, ProfileRegistryParam>();
  const vendorValues: Record<string, number> = {};
  for (const p of prof.registry.parameters) {
    paramSpecs.set(p.parameterId, p);
    vendorValues[p.parameterId] = p.defaultValue;
  }
  if (runObj.parameters) {
    for (const [k, v] of Object.entries(runObj.parameters)) {
      if (paramSpecs.has(k) && Number.isFinite(Number(v))) {
        vendorValues[k] = Number(v);
      }
    }
  }

  const slotBindings = new Map<string, ProfileParameterBinding>();
  for (const b of prof.bindings) {
    for (const slot of b.canonicalTargets) {
      if (!slotBindings.has(slot)) {
        slotBindings.set(slot, b);
      }
    }
  }

  const canonicalToVendor = (
    binding: ProfileParameterBinding,
    canonicalVal: number,
  ): number => {
    const s = binding.scale || 1;
    if (binding.transform === "reciprocal") {
      return canonicalVal > 1e-9 ? s / canonicalVal : 0;
    }
    return (canonicalVal - (binding.offset || 0)) / s;
  };

  const vendorToCanonical = (
    binding: ProfileParameterBinding,
    vendorVal: number,
  ): number => {
    const s = binding.scale || 1;
    if (binding.transform === "reciprocal") {
      return vendorVal > 1e-9 ? s / vendorVal : 0;
    }
    return vendorVal * s + (binding.offset || 0);
  };

  const getCanonicalSlot = (slot: string, fallback: number): number => {
    const b = slotBindings.get(slot);
    if (!b) return fallback;
    const v = vendorValues[b.vendorParameterId];
    return v !== undefined ? vendorToCanonical(b, v) : fallback;
  };

  const makeSuggestion = (
    slot: string,
    targetCanonicalValue: number,
    formula: string,
    effect: string,
    confidence: "High" | "Medium" | "TrendOnly",
    note: string,
  ) => {
    const b = slotBindings.get(slot);
    if (!b || b.tunability === "read-only") return null;
    if (!includeDriveSide && b.tunability === "drive-side") return null;
    const spec = paramSpecs.get(b.vendorParameterId);
    if (!spec) return null;
    const curVal = Number(vendorValues[spec.parameterId] ?? spec.defaultValue);
    const rawTarget = canonicalToVendor(b, targetCanonicalValue);
    const lo = Number(spec.bounds[0]);
    const hi = Number(spec.bounds[1]);
    let sugVal = Math.max(lo, Math.min(hi, rawTarget));
    if (spec.valueType === "integer") {
      sugVal = Math.round(sugVal);
    }
    if (Math.abs(sugVal - curVal) <= Math.max(1e-7, 0.01 * Math.abs(curVal))) {
      return null;
    }
    return {
      parameterId: spec.parameterId,
      displayName: spec.displayName,
      unit: spec.unit,
      tunability: b.tunability,
      currentValue: Number(curVal.toFixed(6)),
      suggestedValue: Number(sugVal.toFixed(6)),
      delta: Number((sugVal - curVal).toFixed(6)),
      mechanismFormula: formula,
      expectedEffect: effect,
      confidenceLevel: confidence,
      verificationNote: note,
    };
  };

  const domPrim = hasArcs
    ? "arc"
    : hasCorners
      ? "corner"
      : hasMicroSegments
        ? "micro-segment-cluster"
        : "line";

  const cmdDev = Number(
    analysis.metrics.sampledPathDeviationMaxMm?.value ?? 0,
  );
  const actDev = actDeviations ? Math.max(...actDeviations) : null;
  const limitMm = caseObj.maximumPathDeviationMm;
  const durS = Number(analysis.metrics.durationSeconds?.value ?? 0);

  const findings: Array<{
    findingId: string;
    severity: "Critical" | "Warning" | "Info";
    symptom: string;
    dominantPrimitive: string;
    errorSource: string;
    observedMetricId: string;
    observedValue: number;
    unit: string;
    suggestions: NonNullable<ReturnType<typeof makeSuggestion>>[];
  }> = [];

  const firTimeS = getCanonicalSlot("fir_time_s", 0.004);
  const notchFreqHz = getCanonicalSlot("notch_freq_hz", 260);
  const cornerTolMm = getCanonicalSlot("corner_tolerance_mm", 0.025);
  const chordTolMm = getCanonicalSlot("small_seg_chord_tol_mm", 0.015);
  const fricX = getCanonicalSlot("friction_comp_amp_x_mm", 0.0);
  const kpX = getCanonicalSlot("servo_kp_x_1_s", 60.0);
  const kpY = getCanonicalSlot("servo_kp_y_1_s", 60.0);
  const pathAcc = getCanonicalSlot("path_tangential_acc_mm_s2", 3000.0);

  // 1. Structural Resonance
  if (dominantResonanceFreqHz >= 45 && resonanceBandRmsMm > 0.0008) {
    const resSugs: NonNullable<ReturnType<typeof makeSuggestion>>[] = [];
    if (prof.capabilities.hasFirFilter) {
      const targetFir = Math.max(firTimeS, 1.0 / dominantResonanceFreqHz);
      const sFir = makeSuggestion(
        "fir_time_s",
        targetFir,
        `FIR 盒式滤波一阶陷波零点：T_fir = 1 / f_res = 1 / ${dominantResonanceFreqHz.toFixed(1)} Hz = ${(1000 / dominantResonanceFreqHz).toFixed(2)} ms`,
        `在指令层直接衰减 ${dominantResonanceFreqHz.toFixed(0)} Hz 附近的机械谐振高频激励`,
        "High",
        "建议先在空运行或试切件上验证表面振纹改善，并检查圆弧/拐角内缩是否超差",
      );
      if (sFir) resSugs.push(sFir);
    }
    if (
      prof.capabilities.hasNotchFilter &&
      Math.abs(notchFreqHz - dominantResonanceFreqHz) > 6.0
    ) {
      const sNotch = makeSuggestion(
        "notch_freq_hz",
        dominantResonanceFreqHz,
        `二阶双二阶陷波器中心频率对齐：f_notch = f_res = ${dominantResonanceFreqHz.toFixed(1)} Hz`,
        `精确滤除驱动侧 ${dominantResonanceFreqHz.toFixed(1)} Hz 结构共振峰`,
        "High",
        "驱动电流环陷波器属于伺服参数，需具备驱动调参权限后单刀验证",
      );
      if (sNotch) resSugs.push(sNotch);
    }
    findings.push({
      findingId: "diag.structural-resonance",
      severity: resonanceBandRmsMm > 0.0025 ? "Critical" : "Warning",
      symptom: `检测到 ${dominantResonanceFreqHz.toFixed(1)} Hz 机械结构谐振峰（频带残差 RMS = ${(resonanceBandRmsMm * 1000).toFixed(1)} um）`,
      dominantPrimitive: domPrim,
      errorSource: "StructuralResonance",
      observedMetricId: "resonanceBandRmsMm",
      observedValue: Number(resonanceBandRmsMm.toFixed(6)),
      unit: "mm",
      suggestions: resSugs,
    });
  }

  // 2. Command planning / filtering over-tolerance
  if (cmdDev > limitMm) {
    const scaleTol = Math.max(
      0.25,
      Math.min(0.85, 0.85 * (limitMm / Math.max(cmdDev, 1e-6))),
    );
    const planSugs: NonNullable<ReturnType<typeof makeSuggestion>>[] = [];
    if (
      domPrim === "micro-segment-cluster" ||
      (hasMicroSegments && !hasCorners)
    ) {
      const sCh = makeSuggestion(
        "small_seg_chord_tol_mm",
        chordTolMm * scaleTol,
        `弦高容差按超限比缩放：tol_new ~= 0.85 * (${limitMm.toFixed(3)} / ${cmdDev.toFixed(3)}) * tol_cur`,
        "收紧密集小线段样条压缩几何偏差，使指令轮廓回到容差门限内",
        "Medium",
        "指令几何误差无需实机试切即可在离线导出轨迹上先行验证",
      );
      if (sCh) planSugs.push(sCh);
    } else {
      if (hasCorners && prof.capabilities.hasCornerBlending) {
        const sCor = makeSuggestion(
          "corner_tolerance_mm",
          cornerTolMm * scaleTol,
          `拐角公差按超限比缩放：eps_new ~= 0.85 * (${limitMm.toFixed(3)} / ${cmdDev.toFixed(3)}) * eps_cur`,
          "减小拐角内切过渡削角量，直接压低指令最大轮廓偏差",
          "Medium",
          "收紧拐角公差会同步降低过弯速度（周期略增，周期变化置信度高）",
        );
        if (sCor) planSugs.push(sCor);
      }
      if (prof.capabilities.hasFirFilter && firTimeS > 0.006) {
        const sFirShrink = makeSuggestion(
          "fir_time_s",
          Math.max(0.002, firTimeS * 0.65),
          "圆弧/拐角滤波内缩近似：dR_fir ~= (v^2 / R) * T_fir^2 / 24",
          "缩短插补后 FIR 滤波时间常数，显著降低圆弧内缩与拐角拖尾削角",
          "High",
          "FIR 内缩量与窗口平方成正比（高置信度），但缩短窗口会提高离散冲击 Jerk",
        );
        if (sFirShrink) planSugs.push(sFirShrink);
      }
    }
    findings.push({
      findingId: "diag.command-over-tolerance",
      severity: "Critical",
      symptom: `指令规划轮廓偏差 ${(cmdDev * 1000).toFixed(1)} um 已超出案例门限 ${(limitMm * 1000).toFixed(1)} um（主导基元：${domPrim}）`,
      dominantPrimitive: domPrim,
      errorSource: "PlanningOrFilter",
      observedMetricId: "sampledPathDeviationMaxMm",
      observedValue: Number(cmdDev.toFixed(6)),
      unit: "mm",
      suggestions: planSugs,
    });
  }

  // 3. Quadrant Crossing Glitch Excess
  if (quadGlitchExcessMm > 0.0025 && (hasArcs || hasXyReversals)) {
    const qSugs: NonNullable<ReturnType<typeof makeSuggestion>>[] = [];
    if (prof.capabilities.hasFrictionCompensation) {
      const sFr = makeSuggestion(
        "friction_comp_amp_x_mm",
        fricX + 0.7 * quadGlitchExcessMm,
        `过象限残差增量补偿：A_fric_new = A_fric_cur + 0.7 * excess (${(quadGlitchExcessMm * 1000).toFixed(1)} um)`,
        "抵消轴向速度过零反向时的静摩擦突跳突起",
        "TrendOnly",
        "摩擦受导轨润滑与温升影响，幅值仅看趋势，必须整圆单刀复测防止过补偿凹陷",
      );
      if (sFr) qSugs.push(sFr);
    }
    findings.push({
      findingId: "diag.quadrant-glitch",
      severity: quadGlitchExcessMm <= 0.006 ? "Warning" : "Critical",
      symptom: `轴过象限反向存在明显摩擦突跳超量（quadrantGlitchExcess = ${(quadGlitchExcessMm * 1000).toFixed(1)} um）`,
      dominantPrimitive: hasArcs ? "arc" : domPrim,
      errorSource: "QuadrantFriction",
      observedMetricId: "quadrantGlitchExcessMm",
      observedValue: Number(quadGlitchExcessMm.toFixed(6)),
      unit: "mm",
      suggestions: qSugs,
    });
  }

  // 4. XY Servo Gain Mismatch
  if (normalServoErrorMaxMm > 0.003 && Math.abs(kpX - kpY) > 3.0) {
    const targetKp = 0.5 * (kpX + kpY);
    const slotMis =
      Math.abs(kpX - targetKp) >= Math.abs(kpY - targetKp)
        ? "servo_kp_x_1_s"
        : "servo_kp_y_1_s";
    const sKp = makeSuggestion(
      slotMis,
      targetKp,
      "双轴联动斜线/圆弧法向偏差：e_mis ~= v * u_x * u_y * |c_v,x - c_v,y|",
      `消除 X/Y 位置环增益失配（当前差值 ${Math.abs(kpX - kpY).toFixed(1)} 1/s）引起的椭圆畸变`,
      "Medium",
      "联动插补轴必须保持等效位置环增益一致；改动驱动增益后请复测整圆球杆仪/光栅轨迹",
    );
    if (sKp) {
      findings.push({
        findingId: "diag.xy-servo-mismatch",
        severity: "Warning",
        symptom: `检测到 X/Y 双轴伺服参数不对称，法向伺服误差峰值达 ${(normalServoErrorMaxMm * 1000).toFixed(1)} um`,
        dominantPrimitive: domPrim,
        errorSource: "ServoTracking",
        observedMetricId: "normalServoErrorMaxMm",
        observedValue: Number(normalServoErrorMaxMm.toFixed(6)),
        unit: "mm",
        suggestions: [sKp],
      });
    }
  }

  // 5. Cycle-Time Efficiency Headroom
  const worstContour = actDev !== null ? Math.max(cmdDev, actDev) : cmdDev;
  if (findings.length === 0 && worstContour <= 0.55 * limitMm) {
    const effSugs: NonNullable<ReturnType<typeof makeSuggestion>>[] = [];
    if (hasCorners && prof.capabilities.hasCornerBlending) {
      const sRelax = makeSuggestion(
        "corner_tolerance_mm",
        Math.min(0.8 * limitMm, cornerTolMm * 1.3),
        "过弯速度包络：v_cor propto sqrt(a_n * eps_cor)，当前精度裕度充足（< 55% 门限）",
        "在精度门限安全裕度内适度放宽拐角公差，提高过弯最低速度并缩短加工周期",
        "High",
        "周期缩短幅度由运动学前瞻白盒决定（高置信度）；实测轮廓增量需上机验证一刀",
      );
      if (sRelax) effSugs.push(sRelax);
    }
    const maxAxAcc = Math.min(
      ...(caseObj.axisLimits ?? []).map((l) => l.maximumAccelerationMmS2),
      10000,
    );
    if (pathAcc < 0.9 * maxAxAcc) {
      const sAcc = makeSuggestion(
        "path_tangential_acc_mm_s2",
        Math.min(maxAxAcc, pathAcc * 1.2),
        "加减速斜坡耗时：t_ramp = dV / a_t，上调 20% 切向加速度压降短线段启停耗时",
        "在不超机床单轴加速度上限的前提下缩短启停过渡时间",
        "High",
        "周期预测置信度高；上调加速度后请留意机台冲击噪声与跟随误差峰值",
      );
      if (sAcc) effSugs.push(sAcc);
    }
    findings.push({
      findingId: "diag.efficiency-headroom",
      severity: "Info",
      symptom: `当前轮廓误差 ${(worstContour * 1000).toFixed(1)} um 远低于门限 ${(limitMm * 1000).toFixed(1)} um（周期 ${durS.toFixed(3)} s），具备提速裕度`,
      dominantPrimitive: domPrim,
      errorSource: "HeadroomAvailable",
      observedMetricId: "durationSeconds",
      observedValue: Number(durS.toFixed(6)),
      unit: "s",
      suggestions: effSugs,
    });
  }

  const sevRank: Record<string, number> = { Critical: 0, Warning: 1, Info: 2 };
  findings.sort((a, b) => (sevRank[a.severity] ?? 9) - (sevRank[b.severity] ?? 9));

  const topActions: NonNullable<ReturnType<typeof makeSuggestion>>[] = [];
  const seenPids = new Set<string>();
  for (const f of findings) {
    for (const sug of f.suggestions) {
      if (!seenPids.has(sug.parameterId) && topActions.length < 2) {
        seenPids.add(sug.parameterId);
        topActions.push(sug);
      }
    }
  }

  const summaryHeadline =
    findings.length === 0
      ? `案例 ${caseObj.caseId}（${prof.vendorName} / ${prof.profileId}）单刀运行正常：周期 ${durS.toFixed(3)} s，最大轮廓偏差 ${(worstContour * 1000).toFixed(1)} um（门限 ${(limitMm * 1000).toFixed(1)} um），无需调参。`
      : `案例 ${caseObj.caseId}（${prof.vendorName} / ${prof.profileId}）识别出 ${findings.length} 项机理问题，优先建议单次调整 ${topActions.length} 个参数后试切验证。`;

  const reportPayload = {
    schemaId: "axiom.cnc-single-run-diagnostic@1",
    caseId: caseObj.caseId,
    controllerProfileId: prof.profileId,
    sourceKind: analysis.sourceKind,
    summaryHeadline,
    cycleTimeConfidence: "High",
    contourErrorConfidence: "TrendOnly",
    confidenceStatement:
      "加工周期与FIR陷波零点频率：基于确定性运动学/频谱白盒公式（高置信度）；实测轮廓与伺服误差数值：受未建模速度环积分、温升摩擦及负载惯量影响，仅作调整方向参考，必须上机验证一刀。",
    findings,
    topActions,
    permissionLevel: "R6-recommend-only",
    deviceWriteAllowed: false,
  };

  return {
    ...reportPayload,
    reportContentHash: deterministicHash(reportPayload),
  };
}
