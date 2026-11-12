import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DiagnosticPlots, Diagnostics } from "./DiagnosticPlots";

const points = [0, 1, 2, 3].map(index => ({ sampleIndex: index * 10, t: index, positionMm: [index, 0, -index], pathDeviationMm: 0.01 * index, velocityMmS: index >= 1 ? [1, 0, -1] : null, accelerationMmS2: index >= 2 ? [0, 0, 0] : null, jerkMmS3: index >= 3 ? [0, 0, 0] : null }));
const data: Diagnostics = { policy: "display subset", baseline: { points, sampleCount: 31, displayCount: 4, exportContentHash: "a" }, candidate: { points, sampleCount: 31, displayCount: 4, exportContentHash: "b" } };
const limits = [0, 1, 2].map(() => ({ minimumPositionMm: -10, maximumPositionMm: 10, maximumVelocityMmS: 2, maximumAccelerationMmS2: 3, maximumJerkMmS3: 4 }));

describe("diagnostic plots", () => {
  it("shows signed per-axis signals, null boundary derivatives and sample navigation", () => {
    render(<DiagnosticPlots data={data} limits={limits} pathLimit={0.02} focus={null} />);
    expect(screen.getAllByRole("img")).toHaveLength(5);
    expect(screen.getByText(/保留正负极值与检查位置/)).toHaveTextContent("4/31");
    expect(screen.getAllByText(/A：未评估/)).toHaveLength(3);
    fireEvent.change(screen.getByLabelText("诊断轴"), { target: { value: "Z" } });
    fireEvent.change(screen.getByLabelText("候选显示样本"), { target: { value: "3" } });
    expect(screen.getByText(/B：样本 30/)).toHaveTextContent("3 s");
    expect(screen.getByText("A：-1 · B：-1 mm/s")).toBeInTheDocument();
    expect(screen.getByText("轴位置 · Z")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("显示约束线"));
    expect(document.querySelectorAll(".cnc-limit-line")).toHaveLength(0);
  });

  it("jumps to the exact retained check location and changes the selected axis", () => {
    const { rerender } = render(<DiagnosticPlots data={data} limits={limits} pathLimit={0.02} focus={null} />);
    fireEvent.change(screen.getByLabelText("候选显示样本"), { target: { value: "1" } });
    rerender(<DiagnosticPlots data={data} limits={limits} pathLimit={0.02} focus={{ sampleIndex: 20, t: 2, axis: "Z" }} />);
    expect(screen.getByLabelText("诊断轴")).toHaveValue("Z");
    expect(screen.getByText(/B：样本 20/)).toBeInTheDocument();
  });
});
