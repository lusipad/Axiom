import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CncBenchmarkWorkbench } from "./CncBenchmarkWorkbench";

const example = {
  case: { caseId: "line", referencePath: [[0, 0, 0], [1, 0, 0]] },
  baseline: { algorithmId: "planner", algorithmVersion: "old", sourceKind: "synthetic-example", samples: [{ positionMm: [0, 0, 0] }, { positionMm: [1, 0, 0] }] },
  candidate: { algorithmId: "planner", algorithmVersion: "new", sourceKind: "synthetic-example", samples: [{ positionMm: [0, 0, 0] }, { positionMm: [0.5, 0.08, 0] }, { positionMm: [1, 0, 0] }] },
};
const check = { checkId: "sampled-path-deviation", value: 0.08, unit: "mm", limit: 0.03, status: "Violated", location: { sampleIndex: 5, t: 0.05, referenceSegmentIndex: 0 } };
const report = {
  caseId: "line", scope: "sampled-xyz-command", outcome: "CandidateViolatesLimits", reportContentHash: "report-id", reasons: [], uncheckedProperties: [],
  baseline: { algorithmId: "planner", algorithmVersion: "old", sourceKind: "synthetic-example", sampleCount: 11, checks: [{ ...check, value: 0, status: "WithinLimit" }], metrics: {} },
  candidate: { algorithmId: "planner", algorithmVersion: "new", sourceKind: "synthetic-example", sampleCount: 11, checks: [check], metrics: {} },
  differences: [{ metricId: "sampledPathDeviationMaxMm", baseline: 0, candidate: 0.08, delta: 0.08, unit: "mm", tolerance: 0.001, status: "Regressed" }, { metricId: "computationSeconds", unit: "s", tolerance: 0, status: "NotComparable", reason: "Both exports must include this measurement" }],
};

function json(body: unknown, status = 200) { return Promise.resolve(new Response(JSON.stringify(body), { status })); }
afterEach(() => vi.unstubAllGlobals());

describe("CNC algorithm comparison", () => {
  it("keeps examples opt-in and reports an independently localized regression", async () => {
    const fetchMock = vi.fn((url: string) => url.endsWith("example") ? json(example) : json(report));
    vi.stubGlobal("fetch", fetchMock);
    render(<CncBenchmarkWorkbench />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "比较 A / B" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "载入回归示例" }));
    await screen.findByText(/当前包含合成示例/);
    fireEvent.click(screen.getByRole("button", { name: "比较 A / B" }));
    expect(await screen.findByRole("heading", { name: "候选超限" })).toBeInTheDocument();
    expect(screen.getByText("样本 5 · 0.05 s · 路径段 0")).toBeInTheDocument();
    expect(screen.getByText("不可比较")).toBeInTheDocument();
    expect(screen.getAllByText("未提供")).toHaveLength(2);
    expect(screen.getByText(/尚未验证采样间连续运动/)).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/benchmarks/cnc/compare");
  });

  it("clears stale evidence and the old input when replacement fails", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("example") ? json(example) : json(report)));
    render(<CncBenchmarkWorkbench />);
    fireEvent.click(screen.getByRole("button", { name: "载入回归示例" }));
    await screen.findByText(/当前包含合成示例/);
    fireEvent.click(screen.getByRole("button", { name: "比较 A / B" }));
    await screen.findByRole("heading", { name: "候选超限" });
    const file = new File(["invalid"], "broken.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => "invalid" });
    fireEvent.change(screen.getByLabelText("选择候选 B文件"), { target: { files: [file] } });
    await screen.findByRole("alert");
    expect(screen.queryByRole("region", { name: "算法比较报告" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "比较 A / B" })).toBeDisabled();
  });

  it("displays incompatible-case errors without retaining a success report", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("example") ? json(example) : json({ detail: [{ loc: ["body", "candidate"], msg: "caseContentHash mismatch" }] }, 422)));
    render(<CncBenchmarkWorkbench />);
    fireEvent.click(screen.getByRole("button", { name: "载入回归示例" }));
    await screen.findByText(/当前包含合成示例/);
    fireEvent.click(screen.getByRole("button", { name: "比较 A / B" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("caseContentHash mismatch");
    await waitFor(() => expect(screen.getByRole("button", { name: "比较 A / B" })).toBeEnabled());
    expect(screen.queryByRole("button", { name: "下载报告" })).not.toBeInTheDocument();
  });
});
