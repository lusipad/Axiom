import { useState } from "react";
import { GUIDE_STAGES, LAB_GUIDE, LAB_SHORT, PIPELINE_ORDER } from "./labGuide";
import type { LabId } from "./labGuide";
import { readStorage, writeStorage } from "./storage";

function storageKey(lab: LabId): string {
  return `axiom-intro-${lab}`;
}

export function LabIntro({ lab, onOpenPipeline }: { lab: LabId; onOpenPipeline: () => void }) {
  const [expanded, setExpanded] = useState(() => readStorage(storageKey(lab)) !== "collapsed");
  const guide = LAB_GUIDE[lab];
  const orderIndex = PIPELINE_ORDER.indexOf(lab);
  const prev = orderIndex > 0 ? PIPELINE_ORDER[orderIndex - 1] : undefined;
  const next = orderIndex >= 0 && orderIndex < PIPELINE_ORDER.length - 1 ? PIPELINE_ORDER[orderIndex + 1] : undefined;
  const stage = GUIDE_STAGES[guide.stageIndex]!;

  const toggle = () => {
    setExpanded((value) => {
      writeStorage(storageKey(lab), value ? "collapsed" : "expanded");
      return !value;
    });
  };

  return (
    <section className="guide-intro" aria-label="实验台说明">
      <div className="guide-intro-row">
        <span className="guide-stage">{guide.stage} · 第 {guide.stageIndex + 1}/{GUIDE_STAGES.length} 阶段</span>
        <strong className="guide-purpose">{guide.purpose}</strong>
        <button type="button" className="guide-link" onClick={onOpenPipeline}>实验路径</button>
        <span className="guide-boundary">{guide.boundaryZh}</span>
        <button
          type="button"
          className="guide-chevron"
          onClick={toggle}
          aria-expanded={expanded}
          aria-label={expanded ? "收起说明" : "展开说明"}
        >
          {expanded ? "▾" : "▸"}
        </button>
      </div>
      {expanded && (
        <div className="guide-detail">
          <p className="guide-question">{stage.question}</p>
          <div className="guide-columns">
            <div>
              <h4>推荐操作</h4>
              <ol>
                {guide.steps.map((step, index) => <li key={index}>{step}</li>)}
              </ol>
            </div>
            <div>
              <h4>结果怎么读</h4>
              <ul>
                {guide.reads.map((read, index) => <li key={index}>{read}</li>)}
              </ul>
            </div>
          </div>
          <p className="guide-nav-hint">
            在整条验证路径中的位置：
            {prev && <span>← 上一步 {LAB_SHORT[prev]}</span>}
            <em>{LAB_SHORT[lab]}</em>
            {next && <span>下一步 {LAB_SHORT[next]} →</span>}
          </p>
        </div>
      )}
    </section>
  );
}
