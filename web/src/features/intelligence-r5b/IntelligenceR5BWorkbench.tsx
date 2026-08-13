import { useEffect, useMemo, useState } from "react";

import type { Catalog, Claim, MetricResult, RunBundle, RunSpec } from "../../types";
import {
  assessRealHoldoutIntake,
  executeR5BRunSpec,
  loadR5BExample,
  loadR5BManifest,
  loadR5BScenarios,
} from "./api";
import type {
  R5BExamplePayload,
  R5BManifest,
  R5BReadinessCheck,
  R5BRunSpec,
  R5BScenarioSummary,
  RealHoldoutIntakeReport,
  RealHoldoutIntakeRequest,
} from "./types";
import "./styles.css";

function shortHash(value?: string | null): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function statusClass(value?: string | boolean | null): string {
  if (
    value === true ||
    value === "Passed" ||
    value === "Succeeded" ||
    value === "Supported"
  ) {
    return "status-positive";
  }
  if (
    value === false ||
    value === "Failed" ||
    value === "Blocked" ||
    value === "Invalid" ||
    value === "Skipped" ||
    value === "Unsupported" ||
    value === "ExecutionFailed" ||
    value === "Refuted"
  ) {
    return "status-negative";
  }
  return "status-neutral";
}

function statusLabel(value: string): string {
  return value.replace(/([a-z])([A-Z])/g, "$1 $2");
}

function formatNumber(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) > 0 && Math.abs(value) < 0.001) return value.toExponential(3);
  return value.toFixed(digits).replace(/\.?0+$/, "");
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function claimLabel(claim?: Claim): string {
  if (!claim) return "Inconclusive";
  return typeof claim.status === "string" ? claim.status : "Inconclusive";
}

function metricValue(metric?: MetricResult): string {
  if (!metric) return "—";
  if (typeof metric.value === "number") {
    return metric.unit === "ratio" ? formatPercent(metric.value) : formatNumber(metric.value);
  }
  if (typeof metric.value === "boolean") return metric.value ? "true" : "false";
  if (typeof metric.value === "string") return metric.value;
  return "—";
}

function compactMetricStatus(status?: string): string {
  if (!status) return "Pending";
  if (status === "InsufficientContext") return "Needs data";
  if (status === "NotApplicable") return "N/A";
  return status;
}

function findMetric(bundle: RunBundle | null, metricId: string): MetricResult | undefined {
  return bundle?.report.metricResults.find((metric) => metric.metricId === metricId);
}

function findRealWorldClaim(bundle: RunBundle | null): Claim | undefined {
  return bundle?.claims.find((claim) =>
    claim.claimDefinitionId === "intelligence.real-world-generalization-claim@1" ||
    claim.predicate.includes("Real-world generalization"),
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRunSpec(value: unknown): value is R5BRunSpec {
  if (!isObject(value)) return false;
  return (
    typeof value.subjectId === "string" &&
    typeof value.domainPackId === "string" &&
    typeof value.runnerId === "string" &&
    isObject(value.request)
  );
}

function parseImportedRunSpec(payload: string): R5BRunSpec {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    throw new Error("导入失败：JSON 解析失败，请提供完整 RunSpec JSON。");
  }
  if (!isRunSpec(parsed)) {
    throw new Error("导入失败：文件不是完整 RunSpec，至少需要 subjectId、domainPackId、runnerId 和 request。");
  }
  return parsed;
}

function parseImportedObject(payload: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    throw new Error(`导入失败：${label} 不是有效 JSON。`);
  }
  if (!isObject(parsed)) {
    throw new Error(`导入失败：${label} 必须是 JSON object。`);
  }
  return parsed;
}

async function readFileAsText(file: File): Promise<string> {
  return file.text();
}

function downloadJson(filename: string, value: unknown): void {
  const blob = new Blob([JSON.stringify(value, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function openChecks(checks: R5BReadinessCheck[]): R5BReadinessCheck[] {
  return checks.filter((item) => item.status === "Open" || item.status === "Failed" || item.status === "Invalid");
}

export function IntelligenceR5BWorkbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<R5BManifest | null>(null);
  const [scenarios, setScenarios] = useState<R5BScenarioSummary[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [example, setExample] = useState<R5BExamplePayload | null>(null);
  const [bundle, setBundle] = useState<RunBundle | null>(null);
  const [busy, setBusy] = useState(true);
  const [executing, setExecuting] = useState<"builtin" | "import" | "intake" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importedSpec, setImportedSpec] = useState<R5BRunSpec | null>(null);
  const [importedFileName, setImportedFileName] = useState<string>("");
  const [submittedRealHoldout, setSubmittedRealHoldout] = useState<boolean | null>(null);
  const [intakeCases, setIntakeCases] = useState<Record<string, unknown>[]>([]);
  const [intakeCaseFiles, setIntakeCaseFiles] = useState<string[]>([]);
  const [intakeGovernance, setIntakeGovernance] = useState<Record<string, unknown> | null>(null);
  const [intakeGovernanceFile, setIntakeGovernanceFile] = useState("");
  const [intakeReport, setIntakeReport] = useState<RealHoldoutIntakeReport | null>(null);
  const [intakeBusy, setIntakeBusy] = useState(false);

  const displayedManifest = example?.manifest ?? manifest;
  const runtimeBound = Boolean(
    displayedManifest?.domainPackId &&
      catalog?.domainPacks.find((item) => item.domainPackId === displayedManifest.domainPackId)?.runtimeBound,
  );
  const unresolvedChecks = useMemo(
    () => openChecks(example?.readinessChecks ?? []),
    [example],
  );
  const realWorldClaim = useMemo(() => findRealWorldClaim(bundle), [bundle]);
  const realWorldMetric = useMemo(
    () => findMetric(bundle, "intelligence.real-world-generalization@1"),
    [bundle],
  );
  const alignmentMetric = useMemo(
    () => findMetric(bundle, "intelligence.r5b.alignment-coverage@1"),
    [bundle],
  );
  const improvementMetric = useMemo(
    () => findMetric(bundle, "intelligence.r5b.x.observed-improvement-ratio@1"),
    [bundle],
  );
  const oodMetric = useMemo(
    () => findMetric(bundle, "intelligence.r5b.x.ood-abstention-rate@1"),
    [bundle],
  );
  const candidateHasRealHoldout = isObject(importedSpec?.request.realHoldoutSet);
  const intakeBaseRunSpec = importedSpec ?? example?.runSpec ?? null;
  const holdoutPresent = bundle
    ? submittedRealHoldout === true
    : Boolean(intakeReport?.realHoldoutSet) || candidateHasRealHoldout || Boolean(example?.realHoldoutSet);

  const loadScenario = async (nextId: string, active?: { value: boolean }) => {
    setBusy(true);
    setBundle(null);
    setSubmittedRealHoldout(null);
    setIntakeReport(null);
    setError(null);
    try {
      const next = await loadR5BExample(nextId);
      if (active && !active.value) return;
      setExample(next);
      setManifest(next.manifest);
      setScenarioId(nextId);
    } catch (reason) {
      if (!active || active.value) {
        setExample(null);
        setError(reason instanceof Error ? reason.message : "R5-B 场景加载失败。");
      }
    } finally {
      if (!active || active.value) setBusy(false);
    }
  };

  const executeRun = async (runSpec: RunSpec, source: "builtin" | "import" | "intake") => {
    setExecuting(source);
    setError(null);
    try {
      const nextBundle = await executeR5BRunSpec(runSpec);
      setBundle(nextBundle);
      setSubmittedRealHoldout(isObject(runSpec.request.realHoldoutSet));
    } catch (reason) {
      setBundle(null);
      setSubmittedRealHoldout(null);
      setError(
        reason instanceof Error
          ? `执行失败：${reason.message}`
          : "执行失败：R5-B 运行返回未知错误。",
      );
    } finally {
      setExecuting(null);
    }
  };

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImportError(null);
    setIntakeReport(null);
    setImportedSpec(null);
    setImportedFileName(file.name);
    try {
      const text = await readFileAsText(file);
      const next = parseImportedRunSpec(text);
      setImportedSpec(next);
    } catch (reason) {
      setImportError(reason instanceof Error ? reason.message : "导入失败：无法读取 RunSpec 文件。");
    } finally {
      event.target.value = "";
    }
  };

  const handleGovernanceImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImportError(null);
    setIntakeReport(null);
    setIntakeGovernance(null);
    setIntakeGovernanceFile(file.name);
    try {
      setIntakeGovernance(parseImportedObject(await readFileAsText(file), "governance 文件"));
    } catch (reason) {
      setImportError(reason instanceof Error ? reason.message : "导入失败：无法读取 governance 文件。");
    } finally {
      event.target.value = "";
    }
  };

  const handleCaseImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;
    setImportError(null);
    setIntakeReport(null);
    setIntakeCases([]);
    setIntakeCaseFiles(files.map((file) => file.name));
    try {
      const cases = await Promise.all(
        files.map(async (file) => parseImportedObject(await readFileAsText(file), `Case ${file.name}`)),
      );
      setIntakeCases(cases);
    } catch (reason) {
      setImportError(reason instanceof Error ? reason.message : "导入失败：无法读取 Case 文件。");
    } finally {
      event.target.value = "";
    }
  };

  const assessIntake = async () => {
    if (!intakeBaseRunSpec || !intakeGovernance || intakeCases.length === 0) return;
    setIntakeBusy(true);
    setImportError(null);
    setIntakeReport(null);
    const request: RealHoldoutIntakeRequest = {
      schemaId: "axiom.intelligence.real-holdout-intake-request@1",
      schemaVersion: 1,
      intakeId: "field.real-holdout-intake@1",
      holdoutSetId: "field.real-holdout-set@1",
      selectionId: "field.real-holdout-selection@1",
      selectedBeforeEvaluation: true,
      baseRunSpec: intakeBaseRunSpec,
      governance: intakeGovernance,
      cases: intakeCases,
    };
    try {
      setIntakeReport(await assessRealHoldoutIntake(request));
    } catch (reason) {
      setImportError(
        reason instanceof Error
          ? `Intake 评估失败：${reason.message}`
          : "Intake 评估失败：服务返回未知错误。",
      );
    } finally {
      setIntakeBusy(false);
    }
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextScenarios] = await Promise.all([
          loadR5BManifest(),
          loadR5BScenarios(),
        ]);
        if (!active.value) return;
        setManifest(nextManifest);
        setScenarios(nextScenarios);
        const defaultId = nextScenarios.some((item) => item.scenarioId === nextManifest.defaultScenarioId)
          ? nextManifest.defaultScenarioId
          : nextScenarios[0]?.scenarioId;
        if (!defaultId) throw new Error("R5-B 场景目录为空。");
        await loadScenario(defaultId, active);
      } catch (reason) {
        if (active.value) {
          setError(reason instanceof Error ? reason.message : "R5-B 初始化失败。");
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
      {(error || importError) && (
        <div className="error-banner" role="alert">
          <strong>R5-B 边界未闭合</strong>
          <span>{error ?? importError}</span>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setImportError(null);
            }}
            aria-label="关闭错误"
          >
            ×
          </button>
        </div>
      )}

      <main className="workspace intelligence-r5b-workspace">
        <aside className="config-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">INTELLIGENCE R5-B</span>
              <h1>Windows 真实 holdout 就绪门</h1>
            </div>
            <span className="schema-badge">v{displayedManifest?.schemaVersion ?? 1}</span>
          </div>

          <section className="config-section">
            <div className="notice-card intelligence-r5b-banner" role="note">
              <strong>{displayedManifest?.safetyBanner ?? "REAL HOLDOUT VALIDATION / NOT DEVICE SAFE"}</strong>
              <strong>{displayedManifest?.realityBanner ?? "NO BUNDLED REAL CAPTURE / CASE-SCOPED EVIDENCE REQUIRED"}</strong>
              <p>仅允许 Windows 只读验证。没有写设备、在线学习、自动部署，也不在仓库内伪造真实 CaseScopedPassed。</p>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>场景</h2><em>{scenarios.length || "—"}</em></div>
            <label className="field-label" htmlFor="r5b-scenario">就绪场景</label>
            <select
              id="r5b-scenario"
              value={scenarioId}
              disabled={busy || intakeBusy || Boolean(executing)}
              onChange={(event) => void loadScenario(event.target.value)}
            >
              {scenarios.map((scenario) => (
                <option key={scenario.scenarioId} value={scenario.scenarioId}>{scenario.title}</option>
              ))}
            </select>
            <p>
              {example
                ? "仓库未内置 controller-export / device-read holdout；真实世界泛化门保持 Open。"
                : "正在加载 R5-B holdout readiness 场景…"}
            </p>
            <div className="chip-row">
              <span className={`chip ${statusClass(displayedManifest?.contractReadinessStatus)}`}>
                contract: {displayedManifest?.contractReadinessStatus ?? "Pending"}
              </span>
              <span className={`chip ${statusClass(displayedManifest?.realWorldGeneralizationStatus)}`}>
                reality: {displayedManifest?.realWorldGeneralizationStatus ?? "Open"}
              </span>
              <span className={`chip ${statusClass(runtimeBound ? "Passed" : "Open")}`}>
                {runtimeBound ? "runtime-bound" : "runtime-pending"}
              </span>
            </div>
            <button
              className="button button-primary top-gap"
              type="button"
              onClick={() => example?.runSpec && void executeRun(example.runSpec, "builtin")}
              disabled={busy || intakeBusy || Boolean(executing) || !example?.runSpec}
            >
              {executing === "builtin" ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
              {executing === "builtin" ? "执行中" : "执行内置 Open 场景"}
            </button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>Open 原因</h2><em>{unresolvedChecks.length || "—"}</em></div>
            <div className="findings-list">
              {unresolvedChecks.map((check) => (
                <article key={check.checkId}>
                  <header>
                    <strong>{check.title}</strong>
                    <span className={statusClass(check.status)}>{check.status}</span>
                  </header>
                  <p>{check.detail}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>Readiness Checklist</h2><em>{example?.readinessChecks.length ?? 0}</em></div>
            <ul className="intelligence-r5b-checks">
              {(example?.readinessChecks ?? []).map((check) => (
                <li key={check.checkId} className={check.status === "Passed" ? "done" : ""}>
                  <span>{check.title}</span>
                  <code className={statusClass(check.status)}>{check.status}</code>
                  <small>{check.detail}</small>
                </li>
              ))}
            </ul>
          </section>

          <section className="config-section">
            <div className="section-title"><span>04</span><h2>身份与回放</h2><em>sealed lineage</em></div>
            <dl className="data-list">
              <div><dt>Manifest</dt><dd title={displayedManifest?.manifestId}>{shortHash(displayedManifest?.manifestId)}</dd></div>
              <div><dt>Domain pack</dt><dd>{displayedManifest?.domainPackId ?? "—"}</dd></div>
              <div><dt>Model bundle</dt><dd>{example?.modelBundle.bundleId ?? "—"}</dd></div>
              <div><dt>Model hash</dt><dd title={example?.modelBundle.contentHash}>{shortHash(example?.modelBundle.contentHash)}</dd></div>
              <div><dt>Interpreter</dt><dd>{example?.modelBundle.targetInterpreterId ?? "—"}</dd></div>
              <div><dt>Dataset</dt><dd>{example?.dataset.datasetId ?? "—"}</dd></div>
              <div><dt>Dataset hash</dt><dd title={example?.dataset.contentHash}>{shortHash(example?.dataset.contentHash)}</dd></div>
              <div><dt>Split</dt><dd>{example?.splitManifest.manifestId ?? "—"}</dd></div>
              <div><dt>Training</dt><dd>{example?.trainingReceipt.receiptId ?? "—"}</dd></div>
              <div><dt>Training method</dt><dd>{example?.trainingReceipt.methodId ?? "—"}</dd></div>
              <div><dt>Parity</dt><dd>{example?.parityReceipt.receiptId ?? "—"}</dd></div>
              <div><dt>Parity gap</dt><dd>{formatNumber(example?.parityReceipt.maxAbsGap, 6)}</dd></div>
              <div><dt>Bundled real holdout</dt><dd>{example?.realHoldoutSet ? "present" : "absent"}</dd></div>
            </dl>
          </section>

          <section className="config-section">
            <div className="section-title"><span>05</span><h2>阈值与证据</h2><em>frozen gate</em></div>
            <div className="intelligence-r5b-threshold-grid">
              <article><span>In-domain</span><strong>{displayedManifest?.acceptanceThresholds.minimumInDomainCases ?? "—"}</strong><small>minimum cases</small></article>
              <article><span>Total</span><strong>{displayedManifest?.acceptanceThresholds.minimumTotalCases ?? "—"}</strong><small>minimum cases</small></article>
              <article><span>Devices</span><strong>{displayedManifest?.acceptanceThresholds.minimumDistinctDevices ?? "—"}</strong><small>distinct in-domain</small></article>
              <article><span>Conditions</span><strong>{displayedManifest?.acceptanceThresholds.minimumDistinctConditions ?? "—"}</strong><small>distinct in-domain</small></article>
              <article><span>Alignment</span><strong>{formatPercent(displayedManifest?.acceptanceThresholds.requiredAlignmentCoverage)}</strong><small>required coverage</small></article>
              <article><span>Improvement</span><strong>{formatPercent(displayedManifest?.acceptanceThresholds.minimumImprovementRatio)}</strong><small>minimum ratio</small></article>
              <article><span>Conformal</span><strong>{formatPercent(displayedManifest?.acceptanceThresholds.minimumConformalCoverage)}</strong><small>minimum coverage</small></article>
              <article><span>OOD abstain</span><strong>{formatPercent(displayedManifest?.acceptanceThresholds.requiredOodAbstentionRate)}</strong><small>required rate</small></article>
              <article><span>Parity gap</span><strong>{formatNumber(displayedManifest?.acceptanceThresholds.maximumTargetParityGap, 6)}</strong><small>maximum abs gap</small></article>
            </div>
            <div className="intelligence-r5b-evidence-list top-gap">
              {(displayedManifest?.requiredEvidence ?? []).map((evidenceId) => (
                <code key={evidenceId}>{evidenceId}</code>
              ))}
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>06</span><h2>现场证据 Intake</h2><em>R7-E → R5-B</em></div>
            <label className="field-label" htmlFor="r5b-governance-file">导入治理记录 JSON</label>
            <input
              id="r5b-governance-file"
              type="file"
              accept="application/json,.json"
              disabled={intakeBusy || Boolean(executing)}
              onChange={(event) => void handleGovernanceImport(event)}
            />
            <p>
              {intakeGovernanceFile
                ? `治理记录：${intakeGovernanceFile}`
                : "需要外部 owner、许可、用途、保留策略、授权和采集完成后的 attestation。"}
            </p>
            <label className="field-label" htmlFor="r5b-intake-case-files">导入 Case JSON（可多选）</label>
            <input
              id="r5b-intake-case-files"
              type="file"
              accept="application/json,.json"
              multiple
              disabled={intakeBusy || Boolean(executing)}
              onChange={(event) => void handleCaseImport(event)}
            />
            <p>
              {intakeCaseFiles.length > 0
                ? `已选择 ${intakeCaseFiles.length} 个 Case：${intakeCaseFiles.join("、")}`
                : "每个文件包含一个现场报告及显式 device/clock/coordinate/lineage/bindings 上下文。"}
            </p>
            <dl className="identity-list intelligence-r5b-import-summary">
              <div><dt>Base RunSpec</dt><dd>{importedSpec ? "imported" : example ? "built-in Open baseline" : "—"}</dd></div>
              <div><dt>Selection</dt><dd>before evaluation</dd></div>
              <div><dt>Cases</dt><dd>{intakeCases.length}</dd></div>
              <div><dt>Safety</dt><dd>NotAssessed</dd></div>
            </dl>
            <button
              className="button button-primary"
              type="button"
              onClick={() => void assessIntake()}
              disabled={intakeBusy || Boolean(executing) || !intakeBaseRunSpec || !intakeGovernance || intakeCases.length === 0}
            >
              {intakeBusy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">⌁</span>}
              {intakeBusy ? "投影中" : "评估并生成 R5-B RunSpec"}
            </button>
            {intakeReport && (
              <div className="intelligence-r5b-intake-result" role="status">
                <strong className={statusClass(intakeReport.intakeStatus)}>{intakeReport.intakeStatus}</strong>
                <span>{intakeReport.projectedCases.length} cases · {shortHash(intakeReport.contentHash)}</span>
              </div>
            )}
            <div className="intelligence-r5b-intake-downloads">
              <button
                className="button button-secondary"
                type="button"
                onClick={() => intakeReport?.realHoldoutSet && downloadJson("r5b-real-holdout-set.json", intakeReport.realHoldoutSet)}
                disabled={!intakeReport?.realHoldoutSet}
              >
                ⇩ 下载 HoldoutSet
              </button>
              <button
                className="button button-secondary"
                type="button"
                onClick={() => intakeReport?.r5bRunSpec && downloadJson("r5b-real-holdout-run-spec.json", intakeReport.r5bRunSpec)}
                disabled={!intakeReport?.r5bRunSpec}
              >
                ⇩ 下载 RunSpec
              </button>
            </div>
            <button
              className="button"
              type="button"
              onClick={() => intakeReport?.r5bRunSpec && void executeRun(intakeReport.r5bRunSpec, "intake")}
              disabled={intakeBusy || Boolean(executing) || !intakeReport?.r5bRunSpec}
            >
              {executing === "intake" ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
              {executing === "intake" ? "执行中" : "执行生成的 R5-B RunSpec"}
            </button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>07</span><h2>导入 RunSpec</h2><em>client-side JSON</em></div>
            <label className="field-label" htmlFor="r5b-runspec-file">导入 RunSpec JSON</label>
            <input
              id="r5b-runspec-file"
              type="file"
              accept="application/json,.json"
              disabled={intakeBusy || Boolean(executing)}
              onChange={(event) => void handleImport(event)}
            />
            <p>
              {importedFileName
                ? `已选择 ${importedFileName}。解析后会直接 POST 公共 /api/v1/runs/evaluate。`
                : "选择完整 RunSpec JSON；只在本地解析，不注入仓库内置真实数据。"}
            </p>
            {importedSpec && (
              <dl className="identity-list intelligence-r5b-import-summary">
                <div><dt>Subject</dt><dd>{importedSpec.subjectId}</dd></div>
                <div><dt>Domain pack</dt><dd>{importedSpec.domainPackId}</dd></div>
                <div><dt>Runner</dt><dd>{importedSpec.runnerId}</dd></div>
                <div><dt>Evaluator</dt><dd>{importedSpec.evaluatorVersion ?? "—"}</dd></div>
              </dl>
            )}
            <button
              className="button"
              type="button"
              onClick={() => importedSpec && void executeRun(importedSpec, "import")}
              disabled={intakeBusy || Boolean(executing) || !importedSpec}
            >
              {executing === "import" ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">⇪</span>}
              {executing === "import" ? "执行中" : "执行导入 RunSpec"}
            </button>
          </section>
        </aside>

        <section className="analysis-panel intelligence-r5b-analysis">
          <div className="analysis-heading">
            <div className="view-tabs" aria-label="R5-B 视图">
              <span>Readiness Gate</span>
              <span>/</span>
              <span>Run Bundle</span>
            </div>
            <div className="run-state">
              <span className={holdoutPresent ? "status-positive" : "status-neutral"}>
                real capture: {holdoutPresent ? "present" : "absent"}
              </span>
              <span className="status-neutral">claim: case-scoped</span>
              <span className="status-negative">device write: blocked</span>
            </div>
          </div>

          <div className="intelligence-r5b-analysis-body">
            <section className="report-card intelligence-r5b-hero">
              <span className="eyebrow">WINDOWS REAL HOLDOUT READINESS</span>
              <div>
                <strong className={statusClass(displayedManifest?.realWorldGeneralizationStatus ?? "Open")}>
                  {displayedManifest?.realWorldGeneralizationStatus ?? "Open"}
                </strong>
                <h2>真实世界泛化门</h2>
                <p>
                  {bundle
                    ? submittedRealHoldout
                      ? `RunBundle: ${bundle.report.caseOutcome}；结论仅限已提交 holdout。`
                      : `RunBundle: ${bundle.report.caseOutcome}；缺少真实配对 holdout。`
                    : "没有 bundled real capture；执行内置场景只会证明该门仍为 Open。"}
                </p>
              </div>
            </section>

            {intakeReport && (
              <section className="report-card intelligence-r5b-intake-report">
                <div className="section-title compact"><span>IN</span><h2>现场证据投影</h2><em>submitted cases only</em></div>
                <div className="intelligence-r5b-intake-summary">
                  <article>
                    <span>Intake</span>
                    <strong className={statusClass(intakeReport.intakeStatus)}>{intakeReport.intakeStatus}</strong>
                    <small>{intakeReport.countsTowardReality ? "可进入 R5-B 评估；尚非泛化结论" : "不可计入 R5-B 现实评估"}</small>
                  </article>
                  <article>
                    <span>Projected cases</span>
                    <strong>{intakeReport.projectedCases.length}</strong>
                    <small>{intakeReport.validationScope}</small>
                  </article>
                  <article>
                    <span>Controlled trial</span>
                    <strong className="status-neutral">{intakeReport.controlledTrialStatus}</strong>
                    <small>closed loop: {intakeReport.closedLoopStatus}</small>
                  </article>
                  <article>
                    <span>Safety</span>
                    <strong className="status-neutral">{intakeReport.deviceSafetyStatus}</strong>
                    <small>process: {intakeReport.processSafetyStatus}</small>
                  </article>
                </div>
                <div className="intelligence-r5b-intake-checks">
                  {intakeReport.checks.map((check) => (
                    <article key={check.checkId}>
                      <header>
                        <strong>{check.title}</strong>
                        <span className={statusClass(check.status)}>{check.status}</span>
                      </header>
                      <code>{check.reasonCode ?? "—"}</code>
                    </article>
                  ))}
                </div>
                <div className="intelligence-r5b-intake-receipts">
                  {intakeReport.projectedCases.map((receipt) => (
                    <article key={receipt.contentHash}>
                      <header>
                        <strong>{receipt.caseId}</strong>
                        <span className={statusClass(receipt.status)}>{receipt.status}</span>
                      </header>
                      <small>source {shortHash(receipt.sourceReportContentHash)}</small>
                      <small>case {shortHash(receipt.caseEvidenceContentHash)}</small>
                      <code>{receipt.reasonCode ?? receipt.timestampPolicyId}</code>
                    </article>
                  ))}
                </div>
              </section>
            )}

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>运行结论</h2><em>case-scoped only</em></div>
              <div className="intelligence-r5b-run-grid">
                <article>
                  <header><strong>Execution</strong><span className={statusClass(bundle?.run.executionStatus)}>{bundle?.run.executionStatus ?? "Not run"}</span></header>
                  <p>{bundle ? `${bundle.run.runnerId} → ${bundle.run.executionStatus}` : "等待内置场景或导入 RunSpec。"}
                  </p>
                </article>
                <article>
                  <header><strong>Bundle</strong><span className={statusClass(bundle?.report.caseOutcome)}>{bundle?.report.caseOutcome ?? "Inconclusive"}</span></header>
                  <p>{bundle
                    ? submittedRealHoldout
                      ? `${bundle.report.caseOutcome}；结论仅限已提交 cases。`
                      : `${bundle.report.caseOutcome}；不发布 CaseScopedPassed。`
                    : "默认保持 Inconclusive。"}
                  </p>
                </article>
                <article>
                  <header><strong>Reality claim</strong><span className={statusClass(realWorldClaim?.status ?? "Inconclusive")}>{claimLabel(realWorldClaim)}</span></header>
                  <p>{realWorldClaim
                    ? submittedRealHoldout
                      ? realWorldClaim.status === "Supported"
                        ? "证据范围仅限本次提交的 Windows holdout cases。"
                        : "已评估提交的 holdout；请按指标和 reasonCode 修正。"
                      : "缺少真实配对 holdout，结论不可闭合。"
                    : "需要外部 Windows 只读 holdout。"}
                  </p>
                </article>
              </div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>02</span><h2>关键指标</h2><em>public run api</em></div>
              <div className="intelligence-r5b-metric-grid">
                {[
                  { metric: findMetric(bundle, "intelligence.r5b.model-integrity@1"), title: "Model integrity" },
                  { metric: realWorldMetric, title: "Real-world generalization" },
                  { metric: alignmentMetric, title: "Alignment coverage" },
                  { metric: improvementMetric, title: "Observed improvement" },
                  { metric: oodMetric, title: "OOD abstention" },
                ].map(({ metric, title }) => (
                  <article key={title}>
                    <header>
                      <strong>{title}</strong>
                      <span className={statusClass(metric?.status)} title={metric?.status}>{compactMetricStatus(metric?.status)}</span>
                    </header>
                    <p>{metricValue(metric)}</p>
                    <small>{metric?.reasonCode ?? "—"}</small>
                  </article>
                ))}
              </div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>03</span><h2>只读真实边界</h2><em>no bundled real data</em></div>
              <div className="findings-list">
                <article>
                  <header><strong>Windows-only</strong><span className={statusClass(displayedManifest?.platform === "windows")}>{displayedManifest?.platform ?? "—"}</span></header>
                  <p>验证器只面向 Windows 接受矩阵；当前仓库默认场景不带 controller-export / device-read holdout。</p>
                </article>
                <article>
                  <header><strong>Real holdout payload</strong><span className={statusClass(holdoutPresent ? "Passed" : "Open")}>{holdoutPresent ? "present" : "absent"}</span></header>
                  <p>{holdoutPresent ? "导入 spec 自带 realHoldoutSet；结论仍限制在提交 cases。" : "request.realHoldoutSet = null，因此真实世界泛化门保持 Open。"}
                  </p>
                </article>
                <article>
                  <header><strong>Forbidden claims</strong><span className="status-negative">blocked</span></header>
                  <p>不提供 DeviceSafe、ProcessSafe、safe-to-run、writeback、online learning 或 auto deployment 控件。</p>
                </article>
              </div>
            </section>
          </div>
        </section>
      </main>
    </>
  );
}
