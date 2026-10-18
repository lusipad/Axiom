import type { FC } from "react";

export const GlobalFooter: FC = () => {
  return (
    <footer className="axiom-global-footer">
      <div className="footer-left">
        Axiom Workbench · 导出格式、Case hash 生成与 CLI 用法见仓库 CNC-BENCHMARK.md
      </div>
      <div className="footer-right">
        可复现实验 · 证据封存 · 不越权
      </div>
    </footer>
  );
};
