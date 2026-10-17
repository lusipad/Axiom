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
