import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { App } from "../App";
import { installDemoFetch } from "./installDemoFetch";

const demoMode = import.meta.env.VITE_DEMO === "1";

const LABS: Array<{ name: RegExp; legacy: boolean }> = [
  { name: /Point Lab/, legacy: true },
  { name: /Five-Axis.*F1/i, legacy: true },
  { name: /Five-Axis.*F2/i, legacy: true },
  { name: /Five-Axis.*F3/i, legacy: true },
  { name: /Five-Axis.*F4/i, legacy: true },
  { name: /Machine.*R3/i, legacy: true },
  { name: /Physical.*R4/i, legacy: true },
  { name: /Intelligence.*R5-A/i, legacy: true },
  { name: /Intelligence.*R5-B/i, legacy: true },
  { name: /Optimization.*R6/i, legacy: true },
  { name: /Controlled.*R7-A/i, legacy: true },
  { name: /Deployment.*R7-B/i, legacy: true },
  { name: /OPC UA.*R7-C/i, legacy: true },
  { name: /Beckhoff.*R7-D/i, legacy: true },
  { name: /Field Evidence/, legacy: true },
];

describe.skipIf(!demoMode)("demo mode lab smoke", () => {
  beforeAll(async () => {
    await installDemoFetch();
  });

  afterEach(() => cleanup());

  it("默认首页不报错", async () => {
    render(<App />);
    const skip = screen.queryByRole("button", { name: "跳过" });
    if (skip) fireEvent.click(skip);
    await new Promise((resolve) => setTimeout(resolve, 800));
    expect(screen.queryByText("未完成")).not.toBeInTheDocument();
  });

  it("现场调参与快诊工作台在 Demo 模式下完整渲染并支持纯前端自定义单刀快诊", async () => {
    render(<App />);
    const skip = screen.queryByRole("button", { name: "跳过" });
    if (skip) fireEvent.click(skip);
    fireEvent.click(screen.getByRole("button", { name: /现场调参与快诊NEW/i }));
    expect(
      await screen.findByText("MD32410 轴跃度滑动滤波时间"),
    ).toBeInTheDocument();
    expect(screen.queryByText("未完成")).not.toBeInTheDocument();

    // Switch to custom single-cut upload and run in-browser local diagnosis
    fireEvent.click(screen.getByRole("button", { name: /\+ 导入自有单刀数据快诊/ }));
    fireEvent.click(screen.getByRole("button", { name: "载入示例模板" }));
    fireEvent.click(screen.getByRole("button", { name: "执行单刀机理快诊" }));

    expect(
      await screen.findByText(/custom\.shopfloor-corner90/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/指令规划轮廓偏差.*已超出案例门限/),
    ).toBeInTheDocument();
  });

  it("纯前端引擎支持任意自定义 A/B 轨迹对比计算", async () => {
    const customPayload = {
      case: {
        caseId: "custom.ab-line",
        coordinateFrame: "workpiece",
        unit: "mm",
        samplePeriodSeconds: 0.01,
        referencePath: [
          [0, 0, 0],
          [10, 0, 0],
        ],
        maximumPathDeviationMm: 0.05,
        maximumEndpointErrorMm: 0.005,
      },
      baseline: {
        algorithmId: "algo.a",
        algorithmVersion: "1.0",
        sourceKind: "algorithm-export",
        samples: [
          { sampleIndex: 0, t: 0, positionMm: [0, 0, 0] },
          { sampleIndex: 1, t: 0.01, positionMm: [2.5, 0.01, 0] },
          { sampleIndex: 2, t: 0.02, positionMm: [5, 0.03, 0] },
          { sampleIndex: 3, t: 0.03, positionMm: [7.5, 0.01, 0] },
          { sampleIndex: 4, t: 0.04, positionMm: [10, 0, 0] },
        ],
      },
      candidate: {
        algorithmId: "algo.b",
        algorithmVersion: "2.0",
        sourceKind: "algorithm-export",
        samples: [
          { sampleIndex: 0, t: 0, positionMm: [0, 0, 0] },
          { sampleIndex: 1, t: 0.01, positionMm: [2.5, 0.001, 0] },
          { sampleIndex: 2, t: 0.02, positionMm: [5, 0.004, 0] },
          { sampleIndex: 3, t: 0.03, positionMm: [7.5, 0.001, 0] },
          { sampleIndex: 4, t: 0.04, positionMm: [10, 0, 0] },
        ],
      },
    };
    const res = await fetch("/api/v1/benchmarks/cnc/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(customPayload),
    });
    expect(res.status).toBe(200);
    const report = await res.json();
    expect(report.schemaId).toBe("axiom.cnc-benchmark-report@1");
    expect(report.caseId).toBe("custom.ab-line");
    expect(report.outcome).toBe("Improved");
  });

  for (const lab of LABS) {
    it(`${lab.name} 打开时不报「未完成」`, async () => {
      render(<App />);
      const skip = screen.queryByRole("button", { name: "跳过" });
      if (skip) fireEvent.click(skip);
      fireEvent.click(screen.getByRole("button", { name: "参考与实验功能" }));
      fireEvent.click(await screen.findByRole("button", { name: lab.name }));
      await new Promise((resolve) => setTimeout(resolve, 1500));
      expect(screen.queryByText("未完成")).not.toBeInTheDocument();
    });
  }
});
