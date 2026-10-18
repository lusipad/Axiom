import type { FC, ReactNode } from "react";

export type NavItem =
  | "benchmark"
  | "point"
  | "five-axis-f1"
  | "five-axis-f2"
  | "five-axis-f3"
  | "five-axis-f4"
  | "machine-r3"
  | "physical-r4"
  | "intelligence-r5"
  | "intelligence-r5b"
  | "optimization-r6"
  | "control-r7"
  | "control-r7b"
  | "control-r7c"
  | "control-r7d"
  | "field-evidence"
  | "pipeline";

interface SidebarProps {
  active: NavItem;
  onSelect: (item: NavItem) => void;
}

interface NavGroup {
  id: string;
  label: string;
  items: {
    id: NavItem;
    label: string;
    icon: ReactNode;
  }[];
}

const IconWrapper: FC<{ children: ReactNode }> = ({ children }) => (
  <span className="sidebar-icon" aria-hidden="true">
    {children}
  </span>
);

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "foundation",
    label: "基础实验",
    items: [
      {
        id: "benchmark",
        label: "A/B 对比",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16 3h5v5" />
              <path d="M4 20L21 3" />
              <path d="M21 16v5h-5" />
              <path d="M15 15l6 6" />
              <path d="M4 4l5 5" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "point",
        label: "点序列实验",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <circle cx="5" cy="12" r="2.2" />
              <circle cx="12" cy="12" r="2.2" />
              <circle cx="19" cy="12" r="2.2" />
            </svg>
          </IconWrapper>
        ),
      },
    ],
  },
  {
    id: "five-axis",
    label: "五轴数学",
    items: [
      {
        id: "five-axis-f1",
        label: "F1 几何",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 8V5a2 2 0 0 1 2-2h3" />
              <path d="M16 3h3a2 2 0 0 1 2 2v3" />
              <path d="M21 16v3a2 2 0 0 1-2 2h-3" />
              <path d="M8 21H5a2 2 0 0 1-2-2v-3" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "five-axis-f2",
        label: "F2 运动学",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "five-axis-f3",
        label: "F3 时间",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9" />
              <polyline points="12 7 12 12 15 15" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "five-axis-f4",
        label: "F4 门禁",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <line x1="4" y1="10" x2="20" y2="10" />
              <line x1="10" y1="4" x2="10" y2="20" />
            </svg>
          </IconWrapper>
        ),
      },
    ],
  },
  {
    id: "physical",
    label: "机床与物理",
    items: [
      {
        id: "machine-r3",
        label: "R3 画像",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <rect x="9" y="9" width="6" height="6" />
              <line x1="9" y1="1" x2="9" y2="4" />
              <line x1="15" y1="1" x2="15" y2="4" />
              <line x1="9" y1="20" x2="9" y2="23" />
              <line x1="15" y1="20" x2="15" y2="23" />
              <line x1="20" y1="9" x2="23" y2="9" />
              <line x1="20" y1="15" x2="23" y2="15" />
              <line x1="1" y1="9" x2="4" y2="9" />
              <line x1="1" y1="15" x2="4" y2="15" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "physical-r4",
        label: "R4 物理",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
              <line x1="12" y1="22.08" x2="12" y2="12" />
            </svg>
          </IconWrapper>
        ),
      },
    ],
  },
  {
    id: "intelligence",
    label: "学习与优化",
    items: [
      {
        id: "intelligence-r5",
        label: "R5-A 合成",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="18" cy="5" r="3" />
              <circle cx="6" cy="12" r="3" />
              <circle cx="18" cy="19" r="3" />
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "intelligence-r5b",
        label: "R5-B 真实门",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "optimization-r6",
        label: "R6 推荐",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="4" y1="21" x2="4" y2="14" />
              <line x1="4" y1="10" x2="4" y2="3" />
              <line x1="12" y1="21" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12" y2="3" />
              <line x1="20" y1="21" x2="20" y2="16" />
              <line x1="20" y1="12" x2="20" y2="3" />
              <line x1="1" y1="14" x2="7" y2="14" />
              <line x1="9" y1="8" x2="15" y2="8" />
              <line x1="17" y1="16" x2="23" y2="16" />
            </svg>
          </IconWrapper>
        ),
      },
    ],
  },
  {
    id: "control",
    label: "控制闭环",
    items: [
      {
        id: "control-r7",
        label: "R7-A 影子",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "control-r7b",
        label: "R7-B 就绪",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "control-r7c",
        label: "R7-C 传输",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="18" cy="18" r="3" />
              <circle cx="6" cy="6" r="3" />
              <circle cx="6" cy="18" r="3" />
              <path d="M18 15v-6a3 3 0 0 0-3-3H9" />
              <path d="M6 9v6" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "control-r7d",
        label: "R7-D 厂商",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 20h20" />
              <path d="M5 20V8l5 4V8l5 4V4h4v16" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "field-evidence",
        label: "R7-E 现场",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 12a10 10 0 0 1 20 0v2H2v-2z" />
              <path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
              <path d="M10 7V3h4v4" />
            </svg>
          </IconWrapper>
        ),
      },
    ],
  },
];

export function Sidebar({ active, onSelect }: SidebarProps) {
  return (
    <aside className="app-sidebar" aria-label="工作台导航">
      <div className="sidebar-brand">
        <div className="sidebar-logo">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 2L4 18h4.5l3.5-7 3.5 7H20L12 2z"
              fill="#00e599"
              fillOpacity="0.25"
              stroke="#00e599"
              strokeWidth="2.2"
              strokeLinejoin="round"
            />
            <path d="M9 13.5h6" stroke="#00e599" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </div>
        <div className="sidebar-brand-text">
          <span className="brand-title">Axiom</span>
          <span className="brand-subtitle">工业算法评估工作台</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV_GROUPS.map((group) => (
          <div key={group.id} className="sidebar-group">
            <div className="sidebar-group-title">{group.label}</div>
            <ul className="sidebar-group-list">
              {group.items.map((item) => {
                const isSelected = active === item.id;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`sidebar-nav-item ${isSelected ? "active" : ""}`}
                      onClick={() => onSelect(item.id)}
                      aria-current={isSelected ? "page" : undefined}
                    >
                      {item.icon}
                      <span className="sidebar-nav-label">{item.label}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <button
          type="button"
          className={`sidebar-nav-item sidebar-pipeline-item ${active === "pipeline" ? "active" : ""}`}
          onClick={() => onSelect("pipeline")}
          aria-current={active === "pipeline" ? "page" : undefined}
        >
          <span className="sidebar-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="6" cy="6" r="3" />
              <circle cx="18" cy="12" r="3" />
              <circle cx="6" cy="18" r="3" />
              <path d="M6 9v6" />
              <path d="M9 6h3a3 3 0 0 1 3 3v3" />
            </svg>
          </span>
          <span className="sidebar-nav-label">验证路径</span>
        </button>
        <div className="sidebar-version">v2.0 · CNC-BENCHMARK.md</div>
      </div>
    </aside>
  );
}
