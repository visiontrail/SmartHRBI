import { isRecord } from "@/lib/utils";
import type { ChartNodeData } from "@/types/workspace";

export function extractChartRows(node: ChartNodeData): Record<string, unknown>[] {
  return extractRowsFromEchartsOption(node.spec.echartsOption);
}

export function extractRowsFromEchartsOption(option: Record<string, unknown>): Record<string, unknown>[] {
  const directRows = normalizeRows(option.__rows__);
  if (directRows.length) {
    return directRows;
  }

  if (isRecord(option.dataset)) {
    const datasetRows = normalizeRows(option.dataset.source);
    if (datasetRows.length) {
      return datasetRows;
    }
  }

  return extractRowsFromAxisSeries(option) || extractRowsFromSeriesData(option.series);
}

function normalizeRows(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const objectRows = value.filter(isRecord);
  if (objectRows.length) {
    return objectRows;
  }

  const [header, ...rows] = value;
  if (!Array.isArray(header) || !header.every((item) => typeof item === "string")) {
    return [];
  }

  return rows
    .filter((row): row is unknown[] => Array.isArray(row))
    .map((row) =>
      header.reduce<Record<string, unknown>>((acc, column, index) => {
        acc[column] = row[index];
        return acc;
      }, {})
    );
}

function extractRowsFromAxisSeries(option: Record<string, unknown>): Record<string, unknown>[] | null {
  const categories = extractAxisData(option.xAxis);
  const seriesItems = Array.isArray(option.series) ? option.series.filter(isRecord) : [];
  if (!categories.length || !seriesItems.length) {
    return null;
  }

  const seriesWithData = seriesItems
    .map((series, index) => ({
      name: typeof series.name === "string" && series.name.trim() ? series.name : `series_${index + 1}`,
      data: Array.isArray(series.data) ? series.data : [],
    }))
    .filter((series) => series.data.length);

  if (!seriesWithData.length) {
    return null;
  }

  return categories.map((category, index) => {
    const row: Record<string, unknown> = { category };
    for (const series of seriesWithData) {
      row[series.name] = normalizeSeriesValue(series.data[index]);
    }
    return row;
  });
}

function extractAxisData(axis: unknown): unknown[] {
  const axisConfig = Array.isArray(axis) ? axis[0] : axis;
  if (!isRecord(axisConfig) || !Array.isArray(axisConfig.data)) {
    return [];
  }
  return axisConfig.data;
}

function extractRowsFromSeriesData(series: unknown): Record<string, unknown>[] {
  const seriesItems = Array.isArray(series) ? series.filter(isRecord) : [];
  const firstSeries = seriesItems.find((item) => Array.isArray(item.data));
  if (!firstSeries || !Array.isArray(firstSeries.data)) {
    return [];
  }

  const rows = normalizeRows(firstSeries.data);
  if (rows.length) {
    return rows;
  }

  return firstSeries.data.map((item, index) => {
    if (isRecord(item) && "name" in item) {
      return {
        name: item.name,
        value: normalizeSeriesValue(item),
      };
    }

    return {
      name: `item-${index + 1}`,
      value: normalizeSeriesValue(item),
    };
  });
}

function normalizeSeriesValue(value: unknown): unknown {
  if (isRecord(value) && "value" in value) {
    return value.value;
  }
  if (Array.isArray(value)) {
    return value.length > 1 ? value[1] : value[0];
  }
  return value;
}
