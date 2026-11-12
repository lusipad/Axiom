import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import workbenchFixture from "../../demo/fixtures/get_api_v1_benchmarks_cnc_param_workbench.json";
import demoFixture from "../../demo/fixtures/get_api_v1_benchmarks_cnc_param_demo.json";
import { clearStorage, readStorage, writeStorage } from "../../guide/storage";
import { CncParamTuningWorkbench } from "./CncParamTuningWorkbench";
import { App } from "../../App";

describe("CncParamTuningWorkbench", () => {
  beforeEach(() => {
    clearStorage();
    writeStorage("axiom-welcomed", "1");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/benchmarks/cnc/param-workbench")) {
          return new Response(JSON.stringify(workbenchFixture), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/api/v1/benchmarks/cnc/param-demo")) {
          return new Response(JSON.stringify(demoFixture), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(JSON.stringify({ detail: "not mocked" }), {
          status: 404,
        });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("switches vendor profiles and enforces NC-only permission filtering", async () => {
    render(<CncParamTuningWorkbench />);

    expect(
      await screen.findByText("MD32520 QEC 过象限摩擦补偿量"),
    ).toBeInTheDocument();
    expect(screen.getByText("MD32410 轴跃度滑动滤波时间")).toBeInTheDocument();

    // Switch to Beckhoff TwinCAT 3 NC
    fireEvent.click(
      screen.getByRole("button", { name: /倍福 TwinCAT 3 NC/i }),
    );
    expect(await screen.findByText("NC 插补滑动平均滤波时间")).toBeInTheDocument();
    expect(screen.getByText("AX5000 驱动器陷波中心频率")).toBeInTheDocument();

    // Toggle NC-only permission lock -> drive-side AX5000 notch must be filtered out
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /仅调 NC 规划参数（锁死伺服驱动器）/i,
      }),
    );
    expect(
      screen.queryByText("AX5000 驱动器陷波中心频率"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("NC 插补滑动平均滤波时间")).toBeInTheDocument();
    expect(
      screen.getByText(/驱动增益\/摩擦补偿建议已按权限自动屏蔽/i),
    ).toBeInTheDocument();

    // Open vendor parameter mapping table
    fireEvent.click(
      screen.getByRole("button", { name: /查看厂商参数映射表/i }),
    );
    expect(screen.getByText("tc.setpoint_pt2_tc_ms")).toBeInTheDocument();
    expect(screen.getByText(/1\/\(2π·τ\)/)).toBeInTheDocument();

    // Safety check: zero buttons imply direct machine control or write
    expect(
      screen.queryByRole("button", {
        name: /写入|控制|应用|启动|复位|下发|急停|连接机床|在线学习|自动部署/i,
      }),
    ).not.toBeInTheDocument();
  });

  it("renders Stage 02 Pareto presets and Stage 03 R3 holdout governance transitions", async () => {
    render(<CncParamTuningWorkbench />);
    await screen.findByText("MD32410 轴跃度滑动滤波时间");

    // Stage 02: Multi-fidelity surrogate & Pareto presets
    fireEvent.click(
      screen.getByRole("tab", { name: /多保真敏感度与三档推荐/i }),
    );
    expect(
      await screen.findByText(/帕累托前沿三档预设/),
    ).toBeInTheDocument();

    // Stage 03: Prediction-Verification Ledger & Governance Gate
    fireEvent.click(
      screen.getByRole("tab", { name: /预测-实测对账与真机门禁/i }),
    );
    expect(
      await screen.findByText(/当前治理判定：Inconclusive/),
    ).toBeInTheDocument();

    // Promote to 3/3 R3 holdout verified
    fireEvent.click(
      screen.getByRole("button", { name: /阶段 B · 满 3 刀独立 R3 真机复切对账达标/i }),
    );
    expect(
      await screen.findByText(/当前治理判定：Passed/),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/vmc-850-shopfloor-01/).length).toBeGreaterThan(0);

    // Thermal drift circuit breaker -> Refuted / Failed
    fireEvent.click(
      screen.getByRole("button", { name: /阶段 C · 现场导轨热漂移失准预警/i }),
    );
    expect(
      await screen.findByText(/当前治理判定：Failed/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Refuted").length).toBeGreaterThan(0);
  });

  it("supports Light/Dark studio theme switching and navigation from App", async () => {
    render(<App />);
    expect(document.documentElement.dataset.theme).toBe("light");

    fireEvent.click(screen.getByRole("button", { name: "深色" }));
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("dark");
      expect(readStorage("axiom-theme")).toBe("dark");
    });

    // Navigate from Sidebar primary workflow item to Param Tuning
    fireEvent.click(
      screen.getByRole("button", { name: /现场调参与快诊NEW/i }),
    );
    expect(
      await screen.findByRole("heading", { name: "现场调参与单刀快诊" }),
    ).toBeInTheDocument();
  });
});
