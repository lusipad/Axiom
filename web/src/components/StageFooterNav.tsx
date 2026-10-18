import type { FC } from "react";
import type { NavItem } from "./Sidebar";

export interface StageStep {
  stage: number;
  name: string;
  labId: NavItem;
}

export const PIPELINE_STAGES: StageStep[] = [
  { stage: 1, name: "A/B 算法对比", labId: "benchmark" },
  { stage: 2, name: "F1 几何", labId: "five-axis-f1" },
  { stage: 3, name: "F2 运动学", labId: "five-axis-f2" },
  { stage: 4, name: "F3 时间", labId: "five-axis-f3" },
  { stage: 5, name: "F4 门禁", labId: "five-axis-f4" },
  { stage: 6, name: "R3·R4 机床与物理", labId: "physical-r4" },
  { stage: 7, name: "R5·R6 学习与推荐", labId: "optimization-r6" },
  { stage: 8, name: "R7 控制闭环", labId: "control-r7" },
];

interface StageFooterNavProps {
  currentStage: number; // 1 to 8
  onSelect: (labId: NavItem) => void;
}

export const StageFooterNav: FC<StageFooterNavProps> = ({ currentStage, onSelect }) => {
  const prevStage = PIPELINE_STAGES.find((s) => s.stage === currentStage - 1);
  const nextStage = PIPELINE_STAGES.find((s) => s.stage === currentStage + 1);

  return (
    <nav className="stage-footer-nav" aria-label="验证路径阶段导航">
      <div className="stage-nav-col prev">
        {prevStage ? (
          <button
            type="button"
            className="stage-nav-button"
            onClick={() => onSelect(prevStage.labId)}
          >
            ← 上一步 · {prevStage.name}
          </button>
        ) : (
          <span />
        )}
      </div>

      <div className="stage-nav-col center">
        <button
          type="button"
          className="stage-nav-center-link"
          onClick={() => onSelect("pipeline")}
        >
          验证路径 · 第 {currentStage} 阶段 / 共 8 步
        </button>
      </div>

      <div className="stage-nav-col next">
        {nextStage ? (
          <button
            type="button"
            className="stage-nav-button"
            onClick={() => onSelect(nextStage.labId)}
          >
            下一步 · {nextStage.name} →
          </button>
        ) : (
          <span />
        )}
      </div>
    </nav>
  );
};
