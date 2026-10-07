import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";

import {
  loadR5IManifest,
  loadR5IMonitoringWindows,
  loadR5IRegistryStatus,
  requestR5IActivePrediction,
  requestR5IPromotionPreflight,
} from "./api";
import type {
  ConditionalEffectPrediction,
  R5IManifest,
  R5IMonitoringWindowReport,
  R5IPromotionPreflightReport,
  R5IRegistryStatus,
} from "./types";

function statusClass(status?: string): string {
  if (status === "Passed" || status === "Healthy" || status === "Eligible") {
    return "status-positive";
  }
  if (
    status === "Blocked"
    || status === "Rejected"
    || status === "Refuted"
    || status === "RollbackRequired"
  ) {
    return "status-negative";
  }
  return "status-neutral";
}

function shortHash(value?: string): string {
  return value ? `${value.slice(0, 9)}…${value.slice(-7)}` : "—";
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

export function R5ILifecyclePanel() {
  const [manifest, setManifest] = useState<R5IManifest | null>(null);
  const [registry, setRegistry] = useState<R5IRegistryStatus | null>(null);
  const [windows, setWindows] = useState<R5IMonitoringWindowReport[]>([]);
  const [promotionRequest, setPromotionRequest] = useState<Record<string, unknown> | null>(null);
  const [promotionFilename, setPromotionFilename] = useState("");
  const [preflight, setPreflight] = useState<R5IPromotionPreflightReport | null>(null);
  const [prediction, setPrediction] = useState<ConditionalEffectPrediction | null>(null);
  const [feedOverride, setFeedOverride] = useState("0.825");
  const [samplePeriod, setSamplePeriod] = useState("0.08");
  const [loading, setLoading] = useState(true);
  const [preflighting, setPreflighting] = useState(false);
  const [predicting, setPredicting] = useState(false);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const active = { value: true };
    (async () => {
      const [manifestResult, statusResult, windowsResult] = await Promise.allSettled([
        loadR5IManifest(),
        loadR5IRegistryStatus(),
        loadR5IMonitoringWindows(),
      ]);
      if (!active.value) return;
      if (
        manifestResult.status === "fulfilled"
        && manifestResult.value.schemaId === "axiom.intelligence.r5i-manifest@1"
      ) {
        setManifest(manifestResult.value);
      } else {
        setError(
          manifestResult.status === "rejected"
            ? errorMessage(manifestResult.reason, "R5-I Manifest 读取失败。")
            : "R5-I Manifest 响应格式无效。",
        );
      }
      if (
        statusResult.status === "fulfilled"
        && statusResult.value.schemaId
          === "axiom.intelligence.model-registry-status@1"
      ) {
        setRegistry(statusResult.value);
      } else {
        setRegistryError(
          statusResult.status === "rejected"
            ? errorMessage(statusResult.reason, "R5-I Registry 未配置。")
            : "R5-I Registry 响应格式无效。",
        );
      }
      if (windowsResult.status === "fulfilled" && Array.isArray(windowsResult.value)) {
        setWindows(windowsResult.value);
      } else if (statusResult.status === "fulfilled") {
        setRegistryError(
          windowsResult.status === "rejected"
            ? errorMessage(windowsResult.reason, "R5-I 监控窗口读取失败。")
            : "R5-I 监控窗口响应格式无效。",
        );
      }
      setLoading(false);
    })();
    return () => {
      active.value = false;
    };
  }, []);

  const importPromotionRequest = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setPreflight(null);
    setError(null);
    if (!file) {
      setPromotionRequest(null);
      setPromotionFilename("");
      return;
    }
    try {
      const value = JSON.parse(await file.text()) as unknown;
      if (
        typeof value !== "object"
        || value === null
        || Array.isArray(value)
        || (value as { schemaId?: string }).schemaId
          !== "axiom.intelligence.promotion-preflight-request@1"
      ) {
        throw new Error("文件必须是 promotion-preflight-request@1 JSON。");
      }
      setPromotionRequest(value as Record<string, unknown>);
      setPromotionFilename(file.name);
    } catch (reason) {
      setPromotionRequest(null);
      setPromotionFilename("");
      setError(errorMessage(reason, "R5-I 提升请求读取失败。"));
    }
  };

  const runPreflight = async () => {
    if (!promotionRequest) return;
    setPreflighting(true);
    setPreflight(null);
    setError(null);
    try {
      setPreflight(await requestR5IPromotionPreflight(promotionRequest));
    } catch (reason) {
      setError(errorMessage(reason, "R5-I 预检失败。"));
    } finally {
      setPreflighting(false);
    }
  };

  const runPrediction = async () => {
    const feed = Number(feedOverride);
    const period = Number(samplePeriod);
    if (!Number.isFinite(feed) || !Number.isFinite(period)) {
      setError("feedOverride 与 samplePeriod 必须是有限数字。");
      return;
    }
    setPredicting(true);
    setPrediction(null);
    setError(null);
    try {
      setPrediction(await requestR5IActivePrediction(feed, period));
    } catch (reason) {
      setError(errorMessage(reason, "R5-I 默认模型推理失败。"));
    } finally {
      setPredicting(false);
    }
  };

  const active = Boolean(registry?.currentModelBundleHash);

  return (
    <section className="report-card intelligence-r5i-lifecycle" aria-label="R5-I 本机模型生命周期">
      <div className="intelligence-r5d-heading">
        <div>
          <span className="eyebrow">SIGNED PREFLIGHT → LOCAL SQLITE → MONITOR → EXPLICIT ROLLBACK</span>
          <h2>R5-I 本机模型生命周期</h2>
          <p>网页只读取 Registry、执行无状态预检与默认模型推理。提升、监控写入和回滚只能由本机 Windows CLI 明确执行。</p>
        </div>
        <div className="intelligence-r5d-status">
          <strong className={active ? "status-positive" : "status-neutral"}>
            {loading ? "Loading" : active ? `Generation ${registry?.generation}` : "No active model"}
          </strong>
          <span>web mutation disabled</span>
        </div>
      </div>

      <div className="notice-card intelligence-r5i-boundary" role="note">
        <strong>{manifest?.safetyBanner ?? "LOCAL MODEL LIFECYCLE ONLY / NO DEVICE DEPLOYMENT / NOT DEVICE SAFE"}</strong>
        <p>此 Registry 只决定 Axiom 本地条件效应模型的默认读取指针；它不是控制器部署、受控试验批准或设备安全证书。</p>
      </div>
      {registryError && <div className="intelligence-r5i-registry-note" role="status"><strong>Registry 不可用</strong><span>{registryError}</span><code>启动服务时显式传入 --r5i-registry</code></div>}
      {error && <div className="intelligence-r5h-error" role="alert">{error}</div>}

      <div className="intelligence-r5i-summary">
        <article><span>Registry</span><strong>{registry?.registryInitialized ? "Initialized" : "Not initialized"}</strong><small>{shortHash(registry?.registryIdentity)}</small></article>
        <article><span>Active model</span><strong>{shortHash(registry?.currentModelBundleHash)}</strong><small>generation {registry?.generation ?? 0}</small></article>
        <article><span>Rollback baseline</span><strong>{shortHash(registry?.rollbackBaselineModelBundleHash)}</strong><small>{registry?.latestEvent?.eventKind ?? "no lifecycle event"}</small></article>
        <article><span>Device path</span><strong className="status-negative">Absent</strong><small>write false · deploy false</small></article>
      </div>

      <div className="intelligence-r5i-grid">
        <section className="intelligence-r5i-pane">
          <div className="section-title compact"><span>01</span><h2>签名提升预检</h2></div>
          <p>导入由 CLI 或审查工具生成的签名请求。服务端只验证证据、独立审查人与授权证明，不写 Registry。</p>
          <div className="intelligence-r5i-actions">
            <label className="button intelligence-r5h-upload">
              <input aria-label="导入 R5-I 提升预检请求" type="file" accept="application/json,.json" onChange={(event) => void importPromotionRequest(event)} />
              导入签名请求
            </label>
            <button className="button button-primary" type="button" onClick={() => void runPreflight()} disabled={!promotionRequest || preflighting}>
              {preflighting ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◇</span>}
              {preflighting ? "权威重放中…" : "只读预检"}
            </button>
          </div>
          <small className="intelligence-r5i-file">{promotionFilename || "尚未选择 promotion-preflight-request@1"}</small>
          {preflight && <div className="intelligence-r5i-preflight" aria-label="R5-I 提升预检结果">
            <div><strong className={statusClass(preflight.overallStatus)}>{preflight.overallStatus}</strong><span>{preflight.promotionTransactionStatus}</span><small>registry write {String(preflight.modelRegistryWritePerformed)}</small></div>
            <div className="intelligence-r5h-checks">{preflight.checks.map((check) => <article key={check.checkId}><div><strong>{check.checkId}</strong><em className={statusClass(check.status)}>{check.status}</em></div><small>{check.reasonCode}</small></article>)}</div>
          </div>}
        </section>

        <section className="intelligence-r5i-pane">
          <div className="section-title compact"><span>02</span><h2>当前默认模型推理</h2></div>
          <p>仅从已提交的本机 Registry 读取默认 bundle；不会更新模型、触发回滚或写入设备。</p>
          <div className="intelligence-r5i-predict-fields">
            <label><span>Feed ratio</span><input aria-label="R5-I feedOverride" type="number" min="0.65" max="1" step="0.001" value={feedOverride} onChange={(event) => setFeedOverride(event.target.value)} /></label>
            <label><span>Sample interval · s</span><input aria-label="R5-I samplePeriod" type="number" min="0.04" max="0.08" step="0.001" value={samplePeriod} onChange={(event) => setSamplePeriod(event.target.value)} /></label>
          </div>
          <button className="button button-primary intelligence-r5i-predict" type="button" onClick={() => void runPrediction()} disabled={!active || predicting}>
            {predicting ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◆</span>}
            {predicting ? "Registry 推理中…" : "使用当前默认模型"}
          </button>
          {prediction && <div className="intelligence-r5i-prediction">{prediction.predictions.map((item) => <article key={item.targetId}><span>{item.targetId}</span><strong>{item.value.toPrecision(7)} {item.unit}</strong><small>[{item.lower.toPrecision(6)}, {item.upper.toPrecision(6)}]</small></article>)}</div>}
        </section>
      </div>

      <section className="intelligence-r5i-monitoring">
        <div className="section-title compact"><span>03</span><h2>持久化监控窗口</h2></div>
        {windows.length === 0 ? <div className="intelligence-r5d-empty"><strong>暂无监控窗口</strong><p>监控证据只能由本机 CLI 写入；网页在这里展示 Healthy、Open 或 RollbackRequired。</p></div> : <div className="intelligence-r5i-window-list">{windows.map((window) => <article key={window.contentHash}><div><strong className={statusClass(window.monitoringStatus)}>{window.monitoringStatus}</strong><span>generation {window.generation}</span></div><code title={window.modelBundleHash}>{shortHash(window.modelBundleHash)}</code><small>{window.targetResults.map((target) => `${target.targetId}: ${target.status}`).join(" · ")}</small></article>)}</div>}
      </section>

      <footer className="intelligence-r5e-boundary intelligence-r5i-footer">
        <strong>网页没有 promote / activate / rollback API</strong>
        <span>Local CLI transaction required: true</span>
        <span>Automatic rollback: false · device write: false</span>
      </footer>
    </section>
  );
}
