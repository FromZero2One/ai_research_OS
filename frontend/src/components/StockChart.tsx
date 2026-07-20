"use client";

import { useRef, useEffect } from "react";
import * as echarts from "echarts";

interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface StockChartProps {
  prices: PricePoint[];
  height?: number;
  showVolume?: boolean;
}

export default function StockChart({ prices, height = 400, showVolume = true }: StockChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current || prices.length === 0) return;

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current, undefined, { renderer: "canvas" });
    }

    const dates = prices.map((p) => p.date.slice(5)); // MM-DD
    const ohlc = prices.map((p) => [p.open, p.close, p.low, p.high]);
    const volumes = prices.map((p) => p.volume);

    // Calculate MA lines
    const ma5 = calcMA(prices, 5);
    const ma20 = calcMA(prices, 20);

    const option: echarts.EChartsOption = {
      backgroundColor: "transparent",
      grid: showVolume
        ? [{ left: "8%", right: "8%", top: "8%", height: "60%" }, { left: "8%", right: "8%", top: "78%", height: "15%" }]
        : [{ left: "8%", right: "8%", top: "8%", bottom: "8%" }],
      xAxis: [
        {
          type: "category",
          data: dates,
          axisLine: { lineStyle: { color: "#2d3140" } },
          axisLabel: { color: "#9aa0a6", fontSize: 10 },
          splitLine: { show: false },
        },
        {
          type: "category",
          gridIndex: 1,
          data: dates,
          axisLabel: { show: false },
          splitLine: { show: false },
        },
      ],
      yAxis: [
        {
          scale: true,
          splitLine: { lineStyle: { color: "#2d3140", type: "dashed" } },
          axisLabel: { color: "#9aa0a6", fontSize: 10 },
        },
        {
          scale: true,
          gridIndex: 1,
          splitLine: { show: false },
          axisLabel: { show: false },
        },
      ],
      series: [
        {
          name: "K 线",
          type: "candlestick",
          data: ohlc,
          itemStyle: {
            color: "#34d399",
            color0: "#f87171",
            borderColor: "#34d399",
            borderColor0: "#f87171",
          },
        },
        {
          name: "MA5",
          type: "line",
          data: ma5,
          smooth: true,
          symbol: "none",
          lineStyle: { width: 1, color: "#fbbf24" },
        },
        {
          name: "MA20",
          type: "line",
          data: ma20,
          smooth: true,
          symbol: "none",
          lineStyle: { width: 1, color: "#4f8cff" },
        },
        ...(showVolume
          ? [
              {
                name: "成交量",
                type: "bar",
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: volumes.map((v, i) => ({
                  value: v,
                  itemStyle: {
                    color: prices[i].close >= prices[i].open ? "#34d399" : "#f87171",
                  },
                })),
              } as any,
            ]
          : []),
      ],
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: "#1a1d28",
        borderColor: "#2d3140",
        textStyle: { color: "#e8eaed", fontSize: 12 },
      },
      legend: {
        data: ["K 线", "MA5", "MA20"],
        textStyle: { color: "#9aa0a6", fontSize: 11 },
        top: 0,
        right: 0,
      },
      dataZoom: [
        { type: "inside", start: Math.max(0, 100 - 120), end: 100 },
        { type: "slider", start: Math.max(0, 100 - 120), end: 100, height: 20, bottom: 0 },
      ],
    };

    instanceRef.current.setOption(option, true);

    const handleResize = () => instanceRef.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [prices, showVolume, height]);

  useEffect(() => {
    return () => instanceRef.current?.dispose();
  }, []);

  if (prices.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-[#9aa0a6]">
        暂无数据
      </div>
    );
  }

  return <div ref={chartRef} style={{ height: `${height}px`, width: "100%" }} />;
}

function calcMA(prices: PricePoint[], days: number): (number | null)[] {
  return prices.map((_, i) => {
    if (i < days - 1) return null;
    let sum = 0;
    for (let j = 0; j < days; j++) sum += prices[i - j].close;
    return Math.round((sum / days) * 100) / 100;
  });
}
