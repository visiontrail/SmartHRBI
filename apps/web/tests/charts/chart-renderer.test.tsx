import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChartRenderer } from "../../components/genui/chart-renderer";

const setOptionMock = vi.fn();
const disposeMock = vi.fn();
const resizeMock = vi.fn();

vi.mock("echarts", () => ({
  init: vi.fn(() => ({
    setOption: setOptionMock,
    dispose: disposeMock,
    resize: resizeMock
  }))
}));

describe("ChartRenderer", () => {
  it("renders recharts bar/line/pie specs", () => {
    const { rerender } = render(
      <ChartRenderer
        spec={{
          engine: "recharts",
          chart_type: "bar",
          title: "Bar",
          data: [{ label: "A", metric_value: 2 }],
          config: { xKey: "label", yKey: "metric_value" }
        }}
      />
    );
    expect(screen.getByTestId("recharts-bar-chart")).toBeInTheDocument();

    rerender(
      <ChartRenderer
        spec={{
          engine: "recharts",
          chart_type: "line",
          title: "Line",
          data: [{ label: "A", metric_value: 2 }],
          config: { xKey: "label", yKey: "metric_value" }
        }}
      />
    );
    expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();

    rerender(
      <ChartRenderer
        spec={{
          engine: "recharts",
          chart_type: "pie",
          title: "Pie",
          data: [{ label: "A", metric_value: 2 }],
          config: { xKey: "label", yKey: "metric_value" }
        }}
      />
    );
    expect(screen.getByTestId("recharts-pie-chart")).toBeInTheDocument();
  }, 10000);

  it("routes high-volume option to echarts renderer", () => {
    const option = {
      xAxis: {
        type: "category",
        data: Array.from({ length: 1000 }, (_, index) => `point-${index}`)
      },
      yAxis: { type: "value" },
      series: [
        {
          type: "line",
          data: Array.from({ length: 1000 }, (_, index) => index)
        }
      ]
    };

    render(
      <ChartRenderer
        spec={{
          engine: "echarts",
          chart_type: "line",
          title: "High Volume",
          data: [],
          config: { option }
        }}
      />
    );

    expect(screen.getByTestId("echarts-chart")).toBeInTheDocument();
    expect(setOptionMock).toHaveBeenCalledWith(option);
  });
});
