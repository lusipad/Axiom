import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LabIntro } from "./LabIntro";
import { PipelineMap } from "./PipelineMap";
import { WelcomeOverlay } from "./WelcomeOverlay";
import { clearStorage, readStorage } from "./storage";

beforeEach(clearStorage);

describe("LabIntro", () => {
  it("展示阶段、用途、推荐操作与结果解读", () => {
    render(<LabIntro lab="five-axis-f2" onOpenPipeline={() => undefined} />);
    expect(screen.getByText(/数学参考/)).toBeInTheDocument();
    expect(screen.getByText("把刀尖路径换算成五个关节的连续运动")).toBeInTheDocument();
    expect(screen.getByText("推荐操作")).toBeInTheDocument();
    expect(screen.getByText("结果怎么读")).toBeInTheDocument();
    expect(screen.getByText(/F1 几何/)).toBeInTheDocument();
    expect(screen.getByText(/F3 时间/)).toBeInTheDocument();
  });

  it("收起后隐藏详情并记住状态", () => {
    const { unmount } = render(<LabIntro lab="point" onOpenPipeline={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "收起说明" }));
    expect(screen.queryByText("推荐操作")).not.toBeInTheDocument();
    unmount();
    render(<LabIntro lab="point" onOpenPipeline={() => undefined} />);
    expect(screen.queryByText("推荐操作")).not.toBeInTheDocument();
  });

  it("点击实验路径打开流水线图", () => {
    const onOpenPipeline = vi.fn();
    render(<LabIntro lab="machine-r3" onOpenPipeline={onOpenPipeline} />);
    fireEvent.click(screen.getByRole("button", { name: "实验路径" }));
    expect(onOpenPipeline).toHaveBeenCalledOnce();
  });
});

describe("PipelineMap", () => {
  it("展示八个阶段并可跳转", () => {
    const onSelect = vi.fn();
    render(<PipelineMap active="control-r7" onSelect={onSelect} onClose={() => undefined} />);
    expect(screen.getByRole("dialog", { name: "实验路径" })).toBeInTheDocument();
    expect(screen.getByText("设备画像")).toBeInTheDocument();
    expect(screen.getByText("现场证据")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /R4 物理/ }));
    expect(onSelect).toHaveBeenCalledWith("physical-r4");
  });

  it("Esc 关闭", () => {
    const onClose = vi.fn();
    render(<PipelineMap active="point" onSelect={() => undefined} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("WelcomeOverlay", () => {
  it("首次展示,完成后不再出现", () => {
    const { unmount } = render(<WelcomeOverlay />);
    expect(screen.getByRole("dialog", { name: "使用引导" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一张" }));
    fireEvent.click(screen.getByRole("button", { name: "下一张" }));
    fireEvent.click(screen.getByRole("button", { name: "开始体验" }));
    unmount();
    render(<WelcomeOverlay />);
    expect(screen.queryByRole("dialog", { name: "使用引导" })).not.toBeInTheDocument();
  });

  it("可以跳过", () => {
    render(<WelcomeOverlay />);
    fireEvent.click(screen.getByRole("button", { name: "跳过" }));
    expect(screen.queryByRole("dialog", { name: "使用引导" })).not.toBeInTheDocument();
    expect(readStorage("axiom-welcomed")).toBe("1");
  });
});
