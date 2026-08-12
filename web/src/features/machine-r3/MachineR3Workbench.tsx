import { useEffect, useMemo, useState } from "react";

import type { Catalog, Claim, MetricResult, RunBundle } from "../../types";
import {
  executeMachineR3Example,
  loadMachineR3Example,
  loadMachineR3Manifest,
  loadMachineR3Scenarios,
} from "./api";
import type {
  MachineR3ExamplePayload,
  MachineR3Manifest,
  MachineR3RunBundle,
  MachineR3ScenarioSummary,
} from "./types";
import "./styles.css";

function shortHash(value?: string | null): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function resultClass(value?: string | boolean | null): string {
  if (
    value === true ||
    value === "Passed" ||
    value === "Succeeded" ||
    value === "Supported" ||
    value === "paired"
  ) {
    return "status-positive";
  }
  if (
    value === false ||
    value === "Failed" ||
    value === "ExecutionFailed" ||
    value === "Refuted" ||
    value === "Rejected" ||
    value === "missing"
  ) {
    return "status-negative";
  }
  return "status-neutral";
}

function formatValue(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/\.?0+$/, "");
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.join(", ");
  return typeof value === "string" ? value : "—";
}

function observedWindow(example: MachineR3ExamplePayload | null): string {
  const frames = example?.artifact.frames ?? [];
  if (!frames.length) return "—";
  return `${frames[0]?.deviceTimestamp ?? "—"} → ${frames.at(-1)?.deviceTimestamp ?? "—"}`;
}

function derivedWarnings(example: MachineR3ExamplePayload | null): Array<{ code: string; severity: "warning" | "error"; message: string }> {
  if (!example) return [];
  const warnings: Array<{ code: string; severity: "warning" | "error"; message: string }> = [];
  if (!example.clockMapping) {
    warnings.push({ code: "ClockAlignmentMissing", severity: "warning", message: "缺少时钟对齐，时间相关 gate 必须降级。" });
  }
  if (!example.coordinateAlignment) {
    warnings.push({ code: "CoordinateAlignmentMissing", severity: "warning", message: "缺少坐标对齐，禁止跨对象比较。" });
  }
  if (example.artifact.captureReceipt.operation !== "file-import") {
    warnings.push({ code: "ForbiddenWriteOperation", severity: "error", message: "检测到非只读操作，R3 应直接阻断。" });
  }
  if ((example.artifact.frames ?? []).some((frame, index, frames) => index > 0 && frame.sequenceId !== frames[index - 1]!.sequenceId + 1)) {
    warnings.push({ code: "FrameSequenceDiscontinuous", severity: "warning", message: "sequenceId 存在断裂或乱序，禁止插值补齐。", });
  }
  if ((example.artifact.frames ?? []).some((frame) => frame.samples.some((sample) => sample.quality === "bad" || sample.quality === "suspect"))) {
    warnings.push({ code: "SampleQualityDegraded", severity: "warning", message: "存在 suspect/bad 样本，需保留原始质量标记。", });
  }
  return warnings;
}

function degradedSamples(example: MachineR3ExamplePayload | null) {
  return (example?.artifact.frames ?? []).flatMap((frame) =>
    frame.samples
      .filter((sample) => sample.quality === "bad" || sample.quality === "suspect")
      .map((sample) => ({ frame, sample })),
  );
}

function discontinuousFrames(example: MachineR3ExamplePayload | null) {
  return (example?.artifact.frames ?? []).filter((frame, index, frames) => index > 0 && frame.sequenceId !== frames[index - 1]!.sequenceId + 1);
}

function flattenedSamples(example: MachineR3ExamplePayload | null) {
  return (example?.artifact.frames ?? []).flatMap((frame) =>
    frame.samples.map((sample) => ({ frame, sample })),
  );
}

function claimText(claim: Claim): string {
  return claim.predicate || claim.claimDefinitionId;
}

function findMetric(bundle: RunBundle | null, metricId: string): MetricResult | undefined {
  return bundle?.report.metricResults.find((metric) => metric.metricId === metricId);
}

function metricChipClass(metric?: MetricResult): string {
  if (!metric) return "status-neutral";
  if (metric.status !== "Computed") return resultClass(metric.status);
  if (metric.value === true) return "status-positive";
  if (metric.value === false) return "status-negative";
  return "status-neutral";
}

function clockChip(example: MachineR3ExamplePayload | null, bundle: MachineR3RunBundle | null): { label: string; tone: string } {
  const metric = findMetric(bundle, "machine-observation.clock-aligned@1");
  if (metric) {
    return {
      label: metric.value === true ? "clock-verified" : "clock-unverified",
      tone: metricChipClass(metric),
    };
  }
  if (!example?.clockMapping) return { label: "missing-clock", tone: "status-negative" };
  if (example.clockMapping.mappingMethod === "synchronized-export") {
    return { label: "clock-synchronized", tone: "status-positive" };
  }
  return { label: `clock-${example.clockMapping.mappingMethod}`, tone: "status-neutral" };
}

function coordinateChip(example: MachineR3ExamplePayload | null, bundle: MachineR3RunBundle | null): { label: string; tone: string } {
  const metric = findMetric(bundle, "machine-observation.coordinate-context@1");
  if (metric) {
    return {
      label: metric.value === true ? "coordinate-verified" : "coordinate-unverified",
      tone: metricChipClass(metric),
    };
  }
  if (!example?.coordinateAlignment) return { label: "missing-coordinate", tone: "status-negative" };
  if (example.coordinateAlignment.calibrationStatus === "calibrated") {
    return { label: "coordinate-calibrated", tone: "status-positive" };
  }
  return { label: "coordinate-estimated", tone: "status-neutral" };
}

function contextHashes(bundle: MachineR3RunBundle | null): Array<{ key: string; value: string }> {
  const candidate = bundle?.run.provenance && typeof bundle.run.provenance === "object"
    ? (bundle.run.provenance as Record<string, unknown>).contextHashes
    : bundle?.report.provenance && typeof bundle.report.provenance === "object"
      ? (bundle.report.provenance as Record<string, unknown>).contextHashes
      : undefined;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return [];
  return Object.entries(candidate)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string")
    .map(([key, value]) => ({ key, value }));
}

export function MachineR3Workbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<MachineR3Manifest | null>(null);
  const [summaries, setSummaries] = useState<MachineR3ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState("read-only-paired-pass");
  const [example, setExample] = useState<MachineR3ExamplePayload | null>(null);
  const [bundle, setBundle] = useState<MachineR3RunBundle | null>(null);
  const [busy, setBusy] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runtimeBound = catalog?.domainPacks.find((item) => item.domainPackId === "machine-observation.domain-pack@1")?.runtimeBound;
  const warnings = useMemo(() => derivedWarnings(example), [example]);
  const degraded = useMemo(() => degradedSamples(example), [example]);
  const channels = useMemo(() => example?.deviceProfile.channels ?? [], [example]);
  const frames = useMemo(() => example?.artifact.frames ?? [], [example]);
  const discontinuities = useMemo(() => discontinuousFrames(example), [example]);
  const samples = useMemo(() => flattenedSamples(example), [example]);
  const claims = bundle?.claims ?? [];
  const clockStatus = useMemo(() => clockChip(example, bundle), [example, bundle]);
  const coordinateStatus = useMemo(() => coordinateChip(example, bundle), [example, bundle]);
  const provenanceHashes = useMemo(() => contextHashes(bundle), [bundle]);

  const loadScenario = async (scenarioId: string, active?: { value: boolean }) => {
    setBusy(true);
    setBundle(null);
    setError(null);
    try {
      const next = await loadMachineR3Example(scenarioId);
      if (active && !active.value) return;
      setExample(next);
      setManifest(next.manifest);
      setSelectedId(scenarioId);
    } catch (reason) {
      if (!active || active.value) {
        setExample(null);
        setError(reason instanceof Error ? reason.message : "Machine R3 场景加载失败。");
      }
    } finally {
      if (!active || active.value) setBusy(false);
    }
  };

  const executeEvaluation = async () => {
    if (!example?.runSpec) return;
    setExecuting(true);
    setError(null);
    try {
      setBundle(await executeMachineR3Example(example));
    } catch (reason) {
      setBundle(null);
      setError(reason instanceof Error ? reason.message : "Machine R3 评估失败。");
    } finally {
      setExecuting(false);
    }
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextSummaries] = await Promise.all([
          loadMachineR3Manifest(),
          loadMachineR3Scenarios(),
        ]);
        if (!active.value) return;
        setManifest(nextManifest);
        setSummaries(nextSummaries);
        const defaultId = nextSummaries.some((item) => item.scenarioId === "read-only-paired-pass")
          ? "read-only-paired-pass"
          : nextSummaries[0]?.scenarioId;
        if (!defaultId) throw new Error("Machine R3 场景目录为空。");
        await loadScenario(defaultId, active);
      } catch (reason) {
        if (active.value) {
          setError(reason instanceof Error ? reason.message : "Machine R3 初始化失败。");
          setBusy(false);
        }
      }
    })();
    return () => {
      active.value = false;
    };
  }, []);

  return (
    <>
      {error && (
        <div className="error-banner" role="alert">
          <strong>R3 未完成</strong><span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="关闭错误">×</button>
        </div>
      )}

      <main className="workspace machine-r3-workspace">
        <aside className="config-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">R3 MACHINE LAB</span>
              <h1>Machine Read-only Lab</h1>
            </div>
            <span className="schema-badge">v{manifest?.schemaVersion ?? 1}</span>
          </div>

          <section className="config-section">
            <div className="notice-card machine-r3-boundary" role="note">
              <strong>{manifest?.safetyBanner ?? "READ ONLY / NOT DEVICE SAFE"}</strong>
              <p>仅允许 Windows 文件导入与评估。禁止写入、启动、参数下发、联锁绕过与安全结论冒充。</p>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>场景</h2><em>{summaries.length || "—"}</em></div>
            <label className="field-label" htmlFor="machine-r3-scenario">场景</label>
            <select
              id="machine-r3-scenario"
              value={selectedId}
              onChange={(event) => void loadScenario(event.target.value)}
              disabled={busy || executing}
            >
              {summaries.map((item) => (
                <option key={item.scenarioId} value={item.scenarioId}>{item.title}</option>
              ))}
            </select>
            <p className="f3-scenario-description">{example?.scenario.description ?? "正在加载 Machine R3 场景…"}</p>
            <div className="chip-row">
              <span className={`chip ${resultClass(example?.lineage.pairingStatus)}`}>{example?.lineage.pairingStatus ?? "—"}</span>
              <span className={`chip ${clockStatus.tone}`}>{clockStatus.label}</span>
              <span className={`chip ${coordinateStatus.tone}`}>{coordinateStatus.label}</span>
            </div>
            <button
              className="button button-primary top-gap"
              type="button"
              onClick={() => void executeEvaluation()}
              disabled={busy || executing || !example?.runSpec}
            >
              {executing ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
              {executing ? "评估中" : "导入观测并评估"}
            </button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>设备身份</h2><em>{runtimeBound ? "runtime" : "pending"}</em></div>
            <dl className="data-list">
              <div><dt>Profile</dt><dd>{example?.deviceProfile.profileId ?? "—"}</dd></div>
              <div><dt>Device</dt><dd>{example?.artifact.deviceIdentity.deviceId ?? "—"}</dd></div>
              <div><dt>Maker</dt><dd>{example?.deviceProfile.manufacturer ?? "—"}</dd></div>
              <div><dt>Family</dt><dd>{example?.artifact.deviceIdentity.controllerFamily ?? "—"}</dd></div>
              <div><dt>Trace Model</dt><dd>{example?.artifact.deviceIdentity.machineModel ?? "—"}</dd></div>
              <div><dt>Profile Model</dt><dd>{example?.deviceProfile.machineModel ?? "—"}</dd></div>
              <div><dt>Export</dt><dd>{example?.deviceProfile.exportVersion ?? "—"}</dd></div>
              <div><dt>Firmware</dt><dd>{example?.deviceProfile.firmwareVersion ?? "—"}</dd></div>
              <div><dt>Allowed Ops</dt><dd>{example?.deviceProfile.allowedReadOnlyOperations.join(", ") ?? "—"}</dd></div>
              <div><dt>Trace</dt><dd>{example?.artifact.traceId ?? "—"}</dd></div>
            </dl>
          </section>
        </aside>

        <section className="analysis-panel machine-r3-analysis">
          <div className="analysis-heading">
            <div className="view-tabs" aria-label="Machine R3 视图">
              <span>Raw Trace</span>
              <span>Derived Alignment</span>
            </div>
            <div className="run-state">
              <span className={resultClass(bundle?.run.executionStatus)}>{bundle?.run.executionStatus ?? "Not run"}</span>
              <span className={resultClass(example?.lineage.pairingStatus)}>{example?.lineage.pairingStatus ?? "—"}</span>
            </div>
          </div>

          <div className="report-columns machine-r3-columns">
            <article className="report-card">
              <h3>Raw Trace</h3>
              <dl className="data-list">
                <div><dt>Receipt</dt><dd>{example?.artifact.captureReceipt.receiptId ?? "—"}</dd></div>
                <div><dt>Source</dt><dd>{example?.artifact.captureReceipt.sourceId ?? "—"}</dd></div>
                <div><dt>Operation</dt><dd>{example?.artifact.captureReceipt.operation ?? "—"}</dd></div>
                <div><dt>Transport</dt><dd>{example?.artifact.captureReceipt.transport ?? "—"}</dd></div>
                <div><dt>Captured</dt><dd>{example?.artifact.captureReceipt.capturedAt ?? "—"}</dd></div>
                <div><dt>Trace Hash</dt><dd title={example?.artifact.captureReceipt.traceContentHash}>{shortHash(example?.artifact.captureReceipt.traceContentHash)}</dd></div>
                <div><dt>Source</dt><dd>{example?.artifact.sourceKind ?? "—"}</dd></div>
                <div><dt>Window</dt><dd>{observedWindow(example)}</dd></div>
                <div><dt>Samples</dt><dd>{frames.length}</dd></div>
                <div><dt>Vendor Meta</dt><dd>{Object.keys(example?.artifact.vendorMetadata ?? {}).join(", ") || "—"}</dd></div>
              </dl>
              <table className="compact-table top-gap">
                <thead><tr><th>Channel</th><th>Kind</th><th>Unit</th><th>Frame</th></tr></thead>
                <tbody>
                  {channels.map((item) => (
                    <tr key={item.channelId}>
                      <td><code>{item.channelId}</code></td>
                      <td>{item.kind}</td>
                      <td>{item.unit ?? "—"}</td>
                      <td>{item.coordinateFrame ?? "—"}</td>
                    </tr>
                  ))}
                  {!channels.length && (
                    <tr><td colSpan={4} className="empty-row">无通道信息</td></tr>
                  )}
                </tbody>
              </table>
            </article>

            <article className="report-card">
              <h3>Derived Alignment</h3>
              <dl className="data-list">
                <div><dt>Lineage</dt><dd className={resultClass(example?.lineage.pairingStatus)}>{example?.lineage.pairingStatus ?? "—"}</dd></div>
                <div><dt>Run</dt><dd>{example?.lineage.machineRunId ?? "—"}</dd></div>
                <div><dt>Baseline</dt><dd title={example?.lineage.baselineRunBundleHash ?? undefined}>{shortHash(example?.lineage.baselineRunBundleHash)}</dd></div>
                <div><dt>Clock</dt><dd className={clockStatus.tone}>{example?.clockMapping ? example.clockMapping.mappingId : "missing"}</dd></div>
                <div><dt>Method</dt><dd>{example?.clockMapping?.mappingMethod ?? "—"}</dd></div>
                <div><dt>Offset</dt><dd>{example?.clockMapping?.offsetMilliseconds ?? "—"}</dd></div>
                <div><dt>Coordinate</dt><dd className={coordinateStatus.tone}>{example?.coordinateAlignment ? example.coordinateAlignment.alignmentId : "missing"}</dd></div>
                <div><dt>Align Source</dt><dd>{example?.coordinateAlignment?.sourceKind ?? "—"}</dd></div>
                <div><dt>Effective</dt><dd>{example?.coordinateAlignment?.effectiveAt ?? "—"}</dd></div>
                <div><dt>Frames</dt><dd>{example?.coordinateAlignment?.machineCoordinateFrame ?? "—"} → {example?.coordinateAlignment?.workCoordinateFrame ?? "—"}</dd></div>
              </dl>

              <div className="findings-list top-gap">
                {warnings.map((warning) => (
                  <article key={`${warning.code}-${warning.message}`}>
                    <header><strong>{warning.code}</strong><span className={warning.severity === "error" ? "status-negative" : "status-neutral"}>{warning.severity}</span></header>
                    <p>{warning.message}</p>
                  </article>
                ))}
                {!warnings.length && <div className="empty-state">无额外告警，仍保持只读边界。</div>}
              </div>

              <table className="compact-table top-gap">
                <thead><tr><th>Channel</th><th>Observed</th><th>Value</th><th>Quality</th></tr></thead>
                <tbody>
                  {degraded.map(({ frame, sample }, index) => (
                    <tr key={`${sample.channelId}-${frame.sequenceId}-${index}`}>
                      <td><code>{sample.channelId}</code></td>
                      <td>{frame.deviceTimestamp}</td>
                      <td>{formatValue(sample.value)}</td>
                      <td>{sample.quality}</td>
                    </tr>
                  ))}
                  {!degraded.length && (
                    <tr><td colSpan={4} className="empty-row">无降级样本</td></tr>
                  )}
                </tbody>
              </table>
            </article>
          </div>

          <div className="metrics-view machine-r3-timeline">
            <table>
              <thead><tr><th>Timestamp</th><th>Sequence</th><th>Channel</th><th>Quality</th><th>Value</th><th>Alarms</th></tr></thead>
              <tbody>
                {samples.map(({ frame, sample }, index) => (
                  <tr key={`${frame.sequenceId}-${sample.channelId}-${index}`}>
                    <td><code>{frame.deviceTimestamp}</code></td>
                    <td>{frame.sequenceId}</td>
                    <td>{sample.channelId}</td>
                    <td className={resultClass(sample.quality === "good" ? true : sample.quality === "bad" ? false : undefined)}>{sample.quality ?? "—"}</td>
                    <td>{formatValue(sample.value)}</td>
                    <td>{frame.alarms?.join(", ") || "—"}</td>
                  </tr>
                ))}
                {!samples.length && (
                  <tr><td colSpan={6} className="empty-row">无观测帧</td></tr>
                )}
              </tbody>
            </table>
            {discontinuities.length > 0 && (
              <div className="empty-state top-gap">存在 {discontinuities.length} 处 sequence discontinuity / gap。</div>
            )}
          </div>
        </section>

        <aside className="evidence-panel">
          <div className="panel-heading evidence-heading">
            <div>
              <span className="eyebrow">SEALED OUTPUT</span>
              <h2>R3 证据</h2>
            </div>
            <span className="schema-badge">{manifest?.suiteId ?? "machine-r3-fixtures@1"}</span>
          </div>

          <section className="verdict-card">
            <span className="eyebrow">RUN VERDICT</span>
            <div className="verdict-row">
              <strong className={resultClass(bundle?.run.caseOutcome)}>{bundle?.run.caseOutcome ?? "Pending"}</strong>
              <span>{bundle ? "只读证据已封存" : "等待评估"}</span>
            </div>
            <div className="verdict-rule"><i /><span>Execution</span><b className={resultClass(bundle?.run.executionStatus)}>{bundle?.run.executionStatus ?? "—"}</b></div>
            <div className="verdict-rule"><i /><span>Runtime bound</span><b className={resultClass(runtimeBound)}>{runtimeBound ? "bound" : "pending"}</b></div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>01</span><h2>冻结身份</h2></div>
            <dl className="identity-list">
              <div><dt>Trace</dt><dd>{example?.artifact.traceId ?? "—"}</dd></div>
              <div><dt>Device</dt><dd>{example?.deviceProfile.deviceId ?? "—"}</dd></div>
              <div><dt>Observation</dt><dd>{bundle?.observation?.source ?? "—"}</dd></div>
              <div><dt>Baseline</dt><dd title={example?.lineage.baselineRunBundleHash ?? undefined}>{shortHash(example?.lineage.baselineRunBundleHash)}</dd></div>
              <div><dt>Bundle</dt><dd title={bundle?.bundleHash}>{shortHash(bundle?.bundleHash)}</dd></div>
            </dl>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>02</span><h2>审计上下文</h2></div>
            <dl className="identity-list">
              {provenanceHashes.map((entry) => (
                <div key={entry.key}>
                  <dt>{entry.key}</dt>
                  <dd title={entry.value}>{shortHash(entry.value)}</dd>
                </div>
              ))}
              {!provenanceHashes.length && (
                <div><dt>Context</dt><dd>—</dd></div>
              )}
            </dl>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>03</span><h2>声明</h2></div>
            <div className="claims-list">
              {claims.map((claim, index) => (
                <article key={`${claim.claimDefinitionId}-${claim.metricId ?? "no-metric"}-${index}`}>
                  <div><strong>{claim.claimDefinitionId}</strong><em className={resultClass(claim.status)}>{claim.status}</em></div>
                  <p>{claimText(claim)}</p>
                  <footer><code>{claim.metricId ?? "no-metric"}</code><span>{claim.evidence?.level ?? "—"}</span></footer>
                </article>
              ))}
              {!claims.length && <div className="empty-state">尚无 claim。</div>}
            </div>
          </section>
        </aside>
      </main>
    </>
  );
}
