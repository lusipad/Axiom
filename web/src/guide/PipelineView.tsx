import type { FC } from "react";
import type { NavItem } from "../components/Sidebar";

interface PipelineStep {
  index: string;
  evidenceLevel: string;
  title: string;
  question: string;
  statusText: string;
  statusType: "completed" | "partial" | "pending";
  actionText?: string;
  subtext?: string;
  labId: NavItem;
}

const STEPS: PipelineStep[] = [
  {
    index: "01",
    evidenceLevel: "证据 L0 · 采样",
    title: "A/B · 算法比较",
    question: "同一案例下，两版算法谁更好？",
    statusText: "已完成 · 报告已封存",
    statusType: "completed",
    actionText: "打开工作台 →",
    labId: "benchmark",
  },
  {
    index: "02",
    evidenceLevel: "证据 L0 · 数学",
    title: "F1 · 几何验证",
    question: "路径分段连续、不越界、无碰撞？",
    statusText: "GeometryValid 通过",
    statusType: "completed",
    actionText: "进入实验台 →",
    labId: "five-axis-f1",
  },
  {
    index: "03",
    evidenceLevel: "证据 L0 · 数学",
    title: "F2 · 运动学",
    question: "五轴关节运动连续且可达？",
    statusText: "M3 链验证通过",
    statusType: "completed",
    actionText: "进入实验台 →",
    labId: "five-axis-f2",
  },
  {
    index: "04",
    evidenceLevel: "证据 L0 · 数学",
    title: "F3 · 时域采样",
    question: "V / A / J 约束与时间律成立？",
    statusText: "部分样本不足",
    statusType: "partial",
    actionText: "进入实验台 →",
    labId: "five-axis-f3",
  },
  {
    index: "05",
    evidenceLevel: "证据 L0 · 数学",
    title: "F4 · 门禁判定",
    question: "数学结论能否收束为一道门禁？",
    statusText: "待运行 · 依赖 F1-F3",
    statusType: "pending",
    subtext: "待前置证据闭合",
    actionText: "进入实验台 →",
    labId: "five-axis-f4",
  },
  {
    index: "06",
    evidenceLevel: "证据 L1 · 只读",
    title: "R3·R4 · 机床与物理",
    question: "设备数据可信、模型与真实一致？",
    statusText: "只读评估 · 未开始",
    statusType: "pending",
    subtext: "待前置证据闭合",
    actionText: "进入实验台 →",
    labId: "physical-r4",
  },
  {
    index: "07",
    evidenceLevel: "证据 L1 · 离线",
    title: "R5·R6 · 学习与推荐",
    question: "模型学到真规律、该调哪些参数？",
    statusText: "离线闭环 · 未开始",
    statusType: "pending",
    subtext: "待前置证据闭合",
    actionText: "进入实验台 →",
    labId: "optimization-r6",
  },
  {
    index: "08",
    evidenceLevel: "证据 L2 · 影子",
    title: "R7 · 控制闭环与现场",
    question: "敢不敢把算法放到真机旁运行？",
    statusText: "Open · 证据未闭合",
    statusType: "partial",
    actionText: "查看门禁 →",
    labId: "control-r7",
  },
];

interface PipelineViewProps {
  onSelect: (labId: NavItem) => void;
  onOpenGuide: () => void;
}

export const PipelineView: FC<PipelineViewProps> = ({ onSelect, onOpenGuide }) => {
  const row1 = STEPS.slice(0, 4);
  const row2 = STEPS.slice(4, 8);

  return (
    <main className="pipeline-page" aria-label="验证路径全景">
      {/* Top Header */}
      <header className="page-header">
        <div className="page-header-info">
          <h1>验证路径</h1>
          <p className="page-header-subtitle">
            从数学到现场的八步 · 每个实验台验证一层假设，结论以可审计声明发布
          </p>
        </div>
        <div className="page-header-actions">
          <button
            type="button"
            className="button button-secondary"
            onClick={onOpenGuide}
          >
            使用引导
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={() => onSelect("benchmark")}
          >
            从 A/B 对比开始
          </button>
        </div>
      </header>

      <div className="pipeline-container">
        {/* Step Cards Grid */}
        <div className="pipeline-track-wrapper">
          <div className="pipeline-row">
            {row1.map((step, idx) => (
              <div key={step.index} className="pipeline-card-container">
                <article className={`pipeline-step-card status-${step.statusType}`}>
                  <header className="card-top-row">
                    <span className="card-step-idx">{step.index}</span>
                    <span className="card-evidence-level">{step.evidenceLevel}</span>
                  </header>
                  <h3 className="card-step-title">{step.title}</h3>
                  <p className="card-step-question">{step.question}</p>

                  <div className="card-footer-area">
                    <span className={`status-pill pill-${step.statusType}`}>
                      {step.statusText}
                    </span>
                    {step.actionText ? (
                      <button
                        type="button"
                        className="card-action-link"
                        onClick={() => onSelect(step.labId)}
                      >
                        {step.actionText}
                      </button>
                    ) : (
                      <span className="card-subtext">{step.subtext}</span>
                    )}
                  </div>
                </article>
                {idx < 3 && <div className="step-arrow-right" aria-hidden="true">→</div>}
              </div>
            ))}
          </div>

          <div className="pipeline-connector-line" aria-hidden="true">
            <svg width="100%" height="40" viewBox="0 0 1000 40" preserveAspectRatio="none">
              <path
                d="M 900 0 L 900 20 L 100 20 L 100 40"
                fill="none"
                stroke="var(--line-strong)"
                strokeWidth="1.5"
                strokeDasharray="4 4"
              />
            </svg>
          </div>

          <div className="pipeline-row">
            {row2.map((step, idx) => (
              <div key={step.index} className="pipeline-card-container">
                <article className={`pipeline-step-card status-${step.statusType}`}>
                  <header className="card-top-row">
                    <span className="card-step-idx">{step.index}</span>
                    <span className="card-evidence-level">{step.evidenceLevel}</span>
                  </header>
                  <h3 className="card-step-title">{step.title}</h3>
                  <p className="card-step-question">{step.question}</p>

                  <div className="card-footer-area">
                    <span className={`status-pill pill-${step.statusType}`}>
                      {step.statusText}
                    </span>
                    {step.subtext && <span className="card-subtext">{step.subtext}</span>}
                    {step.actionText && (
                      <button
                        type="button"
                        className="card-action-link"
                        onClick={() => onSelect(step.labId)}
                      >
                        {step.actionText}
                      </button>
                    )}
                  </div>
                </article>
                {idx < 3 && <div className="step-arrow-right" aria-hidden="true">→</div>}
              </div>
            ))}
          </div>
        </div>

        {/* Design Principles Section */}
        <section className="pipeline-principles-section">
          <h2 className="principles-heading">设计原则</h2>
          <div className="principles-grid">
            <article className="principle-card">
              <div className="principle-icon-wrap icon-green">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                </svg>
              </div>
              <div className="principle-content">
                <h3>可复现</h3>
                <p>所有结论绑定冻结身份与哈希，同一输入随时可重放同一结果。</p>
              </div>
            </article>

            <article className="principle-card">
              <div className="principle-icon-wrap icon-blue">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <path d="M9 15l2 2 4-4" />
                </svg>
              </div>
              <div className="principle-content">
                <h3>可审计</h3>
                <p>每层结论以带证据等级的「声明」发布，附执行链与边界说明。</p>
              </div>
            </article>

            <article className="principle-card">
              <div className="principle-icon-wrap icon-amber">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              </div>
              <div className="principle-content">
                <h3>不越权</h3>
                <p>影子与现场阶段保持只读采集，不写入、不控制任何设备。</p>
              </div>
            </article>
          </div>
        </section>

        {/* Legend Footer Bar */}
        <div className="pipeline-legend-bar">
          <div className="pipeline-legend-items">
            <span className="legend-item">
              <i className="dot dot-completed" /> 已完成
            </span>
            <span className="legend-item">
              <i className="dot dot-partial" /> 部分结论 / 开放
            </span>
            <span className="legend-item">
              <i className="dot dot-pending" /> 待运行
            </span>
          </div>
          <div className="pipeline-legend-note">
            每个实验台验证一层假设；按顺序推进，前面是后面的证据。
          </div>
        </div>
      </div>
    </main>
  );
};
