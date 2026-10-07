export type OptimizationVersion = "v1" | "v2";

export function OptimizationVersionSwitch({
  value,
  onChange,
}: {
  value: OptimizationVersion;
  onChange: (value: OptimizationVersion) => void;
}) {
  return (
    <div className="optimization-version-switch" aria-label="优化器版本">
      <button
        type="button"
        className={value === "v2" ? "active" : ""}
        onClick={() => onChange("v2")}
      >
        v2 · 目标驱动
      </button>
      <button
        type="button"
        className={value === "v1" ? "active" : ""}
        onClick={() => onChange("v1")}
      >
        v1 · Pareto
      </button>
    </div>
  );
}
