import { useEffect } from "react";
import { GUIDE_STAGES, LAB_GUIDE, LAB_SHORT, PIPELINE_ORDER } from "./labGuide";
import type { LabId } from "./labGuide";

const STAGE_LABS: LabId[][] = GUIDE_STAGES.map((_, stageIndex) =>
  PIPELINE_ORDER.filter((lab) => LAB_GUIDE[lab].stageIndex === stageIndex),
);

export function PipelineMap({
  active,
  onSelect,
  onClose,
}: {
  active: LabId;
  onSelect: (lab: LabId) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div className="guide-overlay" role="presentation" onClick={onClose}>
      <div
        className="guide-pipeline"
        role="dialog"
        aria-modal="true"
        aria-label="实验路径"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="guide-pipeline-head">
          <div>
            <span className="guide-stage">验证路径</span>
            <h2>从数学到现场的八步</h2>
            <p>每个实验台验证一层假设,结论以可审计声明发布;按顺序推进,前面是后面的证据。</p>
          </div>
          <button type="button" className="guide-close" onClick={onClose} aria-label="关闭">×</button>
        </header>
        <div className="guide-pipeline-track">
          {GUIDE_STAGES.map((stage, index) => (
            <section className="guide-pnode" key={stage.name}>
              <header>
                <span className="guide-pindex">{String(index + 1).padStart(2, "0")}</span>
                <h3>{stage.name}</h3>
              </header>
              <p className="guide-pquestion">{stage.question}</p>
              <div className="guide-plabs">
                {STAGE_LABS[index]!.map((lab) => (
                  <button
                    key={lab}
                    type="button"
                    className={`guide-plab ${lab === active ? "active" : ""}`}
                    onClick={() => onSelect(lab)}
                  >
                    {lab === active && <i className="guide-youarehere" />}
                    {LAB_SHORT[lab]}
                  </button>
                ))}
              </div>
              {index < GUIDE_STAGES.length - 1 && <span className="guide-parrow" aria-hidden="true">→</span>}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
