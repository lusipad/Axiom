import type { FC } from "react";

export const GlobalFooter: FC = () => {
  return (
    <footer className="axiom-global-footer">
      <div className="footer-left">
        Axiom 数控算法评估与调参工作台 · 采样轨迹核验、灰盒机理快诊与真机对账
      </div>
      <div className="footer-right">
        可复现实验 · 证据封存 · 零设备写权限
      </div>
    </footer>
  );
};
