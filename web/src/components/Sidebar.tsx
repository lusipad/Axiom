import { useEffect, useState } from "react";
import type { FC, ReactNode } from "react";

export type NavItem =
  | "benchmark"
  | "param-tuning"
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

export type ThemeMode = "light" | "dark";

interface SidebarProps {
  active: NavItem;
  onSelect: (item: NavItem) => void;
  theme: ThemeMode;
  onThemeChange: (theme: ThemeMode) => void;
}

interface PrimaryNavItem {
  id: NavItem;
  title: string;
  desc: string;
  badge?: string;
  icon: ReactNode;
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

const PRIMARY_ITEMS: PrimaryNavItem[] = [
  {
    id: "benchmark",
    title: "算法 A/B 对比",
    desc: "采样轨迹评估 · 约束门禁定位",
    icon: (
      <IconWrapper>
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
    id: "param-tuning",
    title: "现场调参与快诊",
    desc: "1刀快诊 · 跨系统参数 · 对账",
    badge: "NEW",
    icon: (
      <IconWrapper>
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
  {
    id: "pipeline",
    title: "验证路径全景",
    desc: "从数学到现场 8 步可审计闭环",
    icon: (
      <IconWrapper>
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="6" cy="6" r="3" />
          <circle cx="18" cy="12" r="3" />
          <circle cx="6" cy="18" r="3" />
          <path d="M6 9v6" />
          <path d="M9 6h3a3 3 0 0 1 3 3v3" />
        </svg>
      </IconWrapper>
    ),
  },
];

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "foundation-five-axis",
    label: "基础与五轴数学",
    items: [
      {
        id: "point",
        label: "点序列实验",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
              <circle cx="5" cy="12" r="2.2" />
              <circle cx="12" cy="12" r="2.2" />
              <circle cx="19" cy="12" r="2.2" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "five-axis-f1",
        label: "F1 几何验证",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
        label: "F2 运动学链",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "five-axis-f3",
        label: "F3 时域采样",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9" />
              <polyline points="12 7 12 12 15 15" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "five-axis-f4",
        label: "F4 验收门禁",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
    id: "physical-intelligence",
    label: "机床物理与学习",
    items: [
      {
        id: "machine-r3",
        label: "R3 只读画像",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <rect x="9" y="9" width="6" height="6" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "physical-r4",
        label: "R4 物理残差",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "intelligence-r5",
        label: "R5-A 合成审查",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
        label: "R5-B 真实留出门",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "optimization-r6",
        label: "R6 离线推荐",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          </IconWrapper>
        ),
      },
    ],
  },
  {
    id: "shadow-field",
    label: "影子门禁与现场",
    items: [
      {
        id: "control-r7",
        label: "R7-A 影子运行",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "control-r7b",
        label: "R7-B 就绪评估",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "control-r7c",
        label: "R7-C 虚拟传输",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
        label: "R7-D 厂商准入",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 20h20" />
              <path d="M5 20V8l5 4V8l5 4V4h4v16" />
            </svg>
          </IconWrapper>
        ),
      },
      {
        id: "field-evidence",
        label: "R7-E 现场证据",
        icon: (
          <IconWrapper>
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 12a10 10 0 0 1 20 0v2H2v-2z" />
              <path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
            </svg>
          </IconWrapper>
        ),
      },
    ],
  },
];

function isUnderlyingLab(item: NavItem): boolean {
  return item !== "benchmark" && item !== "param-tuning" && item !== "pipeline";
}

export function Sidebar({ active, onSelect, theme, onThemeChange }: SidebarProps) {
  const [advancedOpen, setAdvancedOpen] = useState<boolean>(() => isUnderlyingLab(active));

  useEffect(() => {
    if (isUnderlyingLab(active)) {
      setAdvancedOpen(true);
    }
  }, [active]);

  return (
    <aside className="app-sidebar" aria-label="工作台导航">
      <div className="sidebar-brand">
        <div className="sidebar-logo" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 2.5L4.2 18.5h4.3l3.5-7.2 3.5 7.2h4.3L12 2.5z"
              fill="currentColor"
              fillOpacity="0.16"
              stroke="currentColor"
              strokeWidth="2.1"
              strokeLinejoin="round"
            />
            <path d="M9.2 13.8h5.6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </div>
        <div className="sidebar-brand-text">
          <span className="brand-title">Axiom</span>
          <span className="brand-subtitle">数控算法评估与调参工作台</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div>
          <div className="sidebar-section-header">核心工作流</div>
          <ul className="sidebar-primary-list">
            {PRIMARY_ITEMS.map((item) => {
              const isSelected = active === item.id;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`sidebar-primary-item ${isSelected ? "active" : ""}`}
                    onClick={() => onSelect(item.id)}
                    aria-current={isSelected ? "page" : undefined}
                  >
                    {item.icon}
                    <span className="sidebar-primary-copy">
                      <span className="sidebar-primary-title-row">
                        <span className="sidebar-primary-title">{item.title}</span>
                        {item.badge && <span className="sidebar-new-badge">{item.badge}</span>}
                      </span>
                      <span className="sidebar-primary-desc">{item.desc}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="sidebar-advanced-box">
          <button
            type="button"
            className="sidebar-advanced-toggle"
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((prev) => !prev)}
          >
            <span>底层验证实验室 (15)</span>
            <span className={`sidebar-advanced-chevron ${advancedOpen ? "open" : ""}`} aria-hidden="true">
              ▾
            </span>
          </button>

          {advancedOpen && (
            <div className="sidebar-advanced-groups">
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
            </div>
          )}
        </div>
      </nav>

      <div className="sidebar-bottom">
        <div className="theme-segmented" role="group" aria-label="界面主题切换">
          <button
            type="button"
            className={`theme-seg-btn ${theme === "light" ? "active" : ""}`}
            aria-pressed={theme === "light"}
            onClick={() => onThemeChange("light")}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
            </svg>
            浅色
          </button>
          <button
            type="button"
            className={`theme-seg-btn ${theme === "dark" ? "active" : ""}`}
            aria-pressed={theme === "dark"}
            onClick={() => onThemeChange("dark")}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
            深色
          </button>
        </div>
        <div className="sidebar-version">
          <span>v2.1 · 灰盒数控调参版</span>
          <span>离线只读</span>
        </div>
      </div>
    </aside>
  );
}
