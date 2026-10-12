import { useEffect, useState } from "react";

export interface DiagnosticPoint {
  sampleIndex: number; t: number; positionMm: number[]; pathDeviationMm: number;
  velocityMmS: number[] | null; accelerationMmS2: number[] | null; jerkMmS3: number[] | null;
}
interface Series { sampleCount: number; displayCount: number; exportContentHash: string; points: DiagnosticPoint[] }
export interface Diagnostics { policy: string; baseline: Series; candidate: Series }
interface AxisLimit { minimumPositionMm: number; maximumPositionMm: number; maximumVelocityMmS: number; maximumAccelerationMmS2: number; maximumJerkMmS3: number }
export interface FocusLocation { sampleIndex: number; t: number; axis?: string }
type Field = "positionMm" | "pathDeviationMm" | "velocityMmS" | "accelerationMmS2" | "jerkMmS3";
const charts: [Field, string, string][] = [["positionMm", "轴位置", "mm"], ["pathDeviationMm", "采样路径偏差", "mm"], ["velocityMmS", "离散速度", "mm/s"], ["accelerationMmS2", "离散加速度", "mm/s²"], ["jerkMmS3", "离散 Jerk", "mm/s³"]];
const fmt = (value: number) => Number(value.toPrecision(6)).toString();
const valueAt = (point: DiagnosticPoint, field: Field, axis: number) => field === "pathDeviationMm" ? point.pathDeviationMm : point[field]?.[axis] ?? null;

export function DiagnosticPlots({ data, limits, pathLimit, focus }: { data: Diagnostics; limits: AxisLimit[]; pathLimit: number; focus: FocusLocation | null }) {
  const [axisName, setAxisName] = useState("X");
  const [selection, setSelection] = useState(0);
  const [showLimits, setShowLimits] = useState(true);
  const [useFocus, setUseFocus] = useState(true);
  useEffect(() => setUseFocus(true), [focus]);
  const axis = ["X", "Y", "Z"].indexOf(useFocus && focus?.axis ? focus.axis : axisName);
  const candidate = data.candidate.points;
  if (!candidate.length || !data.baseline.points.length) return <p>诊断序列为空，无法绘图。</p>;
  const focusedIndex = focus ? candidate.findIndex(point => point.sampleIndex === focus.sampleIndex) : -1;
  const selected = candidate[useFocus && focusedIndex >= 0 ? focusedIndex : Math.min(selection, candidate.length - 1)];
  if (!selected) return <p>未找到显示样本，无法定位。</p>;
  const baselinePoint = data.baseline.points.reduce((best, point) => Math.abs(point.t - selected.t) < Math.abs(best.t - selected.t) ? point : best);
  const maxTime = Math.max(candidate[candidate.length - 1]?.t ?? 0, data.baseline.points[data.baseline.points.length - 1]?.t ?? 0, 1e-12);
  const limit = limits[axis];
  const selectPoint = (index: number) => { setSelection(index); setUseFocus(false); };
  return <section className="cnc-diagnostics" aria-label="采样时域诊断">
    <h3>时域诊断：从指标回到样本</h3>
    <div className="cnc-chart-controls">
      <label>诊断轴 <select aria-label="诊断轴" value={["X", "Y", "Z"][axis]} onChange={event => { setAxisName(event.target.value); setUseFocus(false); }}>{["X", "Y", "Z"].map(name => <option key={name}>{name}</option>)}</select></label>
      <label><input type="checkbox" checked={showLimits} onChange={event => setShowLimits(event.target.checked)} /> 显示约束线</label>
      {focus && <button className="cnc-link" type="button" onClick={() => setUseFocus(true)}>返回选中检查位置</button>}
      <span>蓝色虚线 A · 橙色实线 B · 灰色点线限制</span>
    </div>
    <p className="cnc-muted">全样本计算；图表显示 A {data.baseline.displayCount}/{data.baseline.sampleCount}、B {data.candidate.displayCount}/{data.candidate.sampleCount} 点，保留正负极值与检查位置。连接线仅用于阅读，不代表采样间运动。</p>
    <label className="cnc-scrubber">候选显示样本（方向键可定位）<input aria-label="候选显示样本" type="range" min="0" max={candidate.length - 1} value={useFocus && focusedIndex >= 0 ? focusedIndex : Math.min(selection, candidate.length - 1)} onChange={event => selectPoint(Number(event.target.value))} /></label>
    <p aria-live="polite">B：样本 {selected.sampleIndex} · {fmt(selected.t)} s；A 最近显示样本 {baselinePoint.sampleIndex} · {fmt(baselinePoint.t)} s。不作重采样或时间对齐。</p>
    <div className="cnc-chart-grid">{charts.map(([field, title, unit]) => {
      const bands = !limit ? [] : field === "positionMm" ? [limit.minimumPositionMm, limit.maximumPositionMm] : field === "pathDeviationMm" ? [pathLimit] : field === "velocityMmS" ? [-limit.maximumVelocityMmS, limit.maximumVelocityMmS] : field === "accelerationMmS2" ? [-limit.maximumAccelerationMmS2, limit.maximumAccelerationMmS2] : [-limit.maximumJerkMmS3, limit.maximumJerkMmS3];
      const values = [data.baseline, data.candidate].flatMap(series => series.points.map(point => valueAt(point, field, axis)).filter((value): value is number => value !== null));
      if (!values.length) return <figure className="cnc-preview" key={field}><figcaption>{title}</figcaption><p>样本不足，未推断边界状态。</p></figure>;
      const extrema = [...values, ...(showLimits ? bands : []), 0];
      const min = Math.min(...extrema), max = Math.max(...extrema), span = Math.max(max - min, 1e-12);
      const y = (value: number) => 155 - (value - min) / span * 125;
      const x = (t: number) => 65 + t / maxTime * 610;
      const aValue = valueAt(baselinePoint, field, axis), bValue = valueAt(selected, field, axis);
      return <figure className="cnc-preview" key={field}>
        <figcaption><strong>{title}{field !== "pathDeviationMm" && ` · ${["X", "Y", "Z"][axis]}`}</strong><span>{unit}</span></figcaption>
        <svg viewBox="0 0 710 200" role="img" aria-label={`${title}随时间变化，${unit}`} onClick={event => {
          const rect = event.currentTarget.getBoundingClientRect();
          if (rect.width <= 0) return;
          const t = Math.max(0, Math.min(maxTime, ((event.clientX - rect.left) / rect.width * 710 - 65) / 610 * maxTime));
          selectPoint(candidate.reduce((best, point, index) => Math.abs(point.t - t) < Math.abs((candidate[best]?.t ?? 0) - t) ? index : best, 0));
        }}>
          <path d="M65 25V160H680" className="cnc-grid" />
          <text x="2" y="32">{fmt(max)}</text><text x="2" y="157">{fmt(min)}</text><text x="65" y="185">0 s</text><text x="590" y="185">{fmt(maxTime)} s</text>
          {showLimits && bands.map((band, index) => <line key={index} x1="65" x2="675" y1={y(band)} y2={y(band)} className="cnc-limit-line" />)}
          {[data.baseline, data.candidate].map((series, index) => <polyline key={index} className={index === 0 ? "baseline" : "candidate"} points={series.points.flatMap(point => { const value = valueAt(point, field, axis); return value === null ? [] : [`${x(point.t)},${y(value)}`]; }).join(" ")} />)}
          <line x1={x(selected.t)} x2={x(selected.t)} y1="25" y2="160" className="cnc-cursor-line" />
          {bValue !== null && <circle cx={x(selected.t)} cy={y(bValue)} r="4" className="cnc-selected-point" />}
        </svg>
        <p>A：{aValue === null ? "未评估" : fmt(aValue)} · B：{bValue === null ? "未评估" : fmt(bValue)} {unit}</p>
      </figure>;
    })}</div>
  </section>;
}
