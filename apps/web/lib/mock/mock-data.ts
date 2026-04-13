import type { ChatSession, ChatMessage, AssistantResponse } from "@/types/chat";
import type { ChartAsset, ChartSpec } from "@/types/chart";
import type { Workspace, WorkspaceSnapshot } from "@/types/workspace";

// ─── Chart Specs ────────────────────────────────────────────────────────────

export const MOCK_CHART_SPECS: Record<string, ChartSpec> = {
  departmentHeadcount: {
    chartType: "bar",
    title: "Headcount by Department",
    subtitle: "Current employee distribution across departments",
    echartsOption: {
      tooltip: { trigger: "axis" },
      grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
      xAxis: {
        type: "category",
        data: ["Engineering", "Product", "Design", "Marketing", "Sales", "HR", "Finance", "Operations"],
        axisLabel: { rotate: 15, fontSize: 11 },
      },
      yAxis: { type: "value", name: "Headcount" },
      series: [{
        name: "Headcount",
        type: "bar",
        data: [156, 42, 38, 35, 67, 18, 22, 31],
        itemStyle: { color: "#c96442", borderRadius: [4, 4, 0, 0] },
        emphasis: { itemStyle: { color: "#d97757" } },
      }],
    },
  },

  turnoverTrend: {
    chartType: "line",
    title: "Monthly Turnover Rate",
    subtitle: "12-month rolling turnover trend",
    echartsOption: {
      tooltip: { trigger: "axis" },
      grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
      xAxis: {
        type: "category",
        data: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
      },
      yAxis: { type: "value", name: "Rate (%)", axisLabel: { formatter: "{value}%" } },
      series: [{
        name: "Turnover Rate",
        type: "line",
        data: [3.2, 2.8, 3.5, 4.1, 3.8, 3.2, 2.9, 3.6, 4.2, 3.9, 3.1, 2.7],
        smooth: true,
        lineStyle: { color: "#c96442", width: 3 },
        itemStyle: { color: "#c96442" },
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(201,100,66,0.25)" }, { offset: 1, color: "rgba(201,100,66,0.02)" }] } },
      }],
    },
  },

  salaryDistribution: {
    chartType: "pie",
    title: "Salary Band Distribution",
    subtitle: "Employee count by compensation tier",
    echartsOption: {
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { orient: "vertical", right: "5%", top: "center" },
      series: [{
        name: "Salary Band",
        type: "pie",
        radius: ["35%", "65%"],
        center: ["40%", "50%"],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: "#faf9f5", borderWidth: 2 },
        label: { show: true, formatter: "{b}\n{d}%" },
        data: [
          { value: 45, name: "< ¥15K", itemStyle: { color: "#d1cfc5" } },
          { value: 128, name: "¥15K-25K", itemStyle: { color: "#b0aea5" } },
          { value: 96, name: "¥25K-40K", itemStyle: { color: "#c96442" } },
          { value: 72, name: "¥40K-60K", itemStyle: { color: "#d97757" } },
          { value: 34, name: "> ¥60K", itemStyle: { color: "#87867f" } },
        ],
      }],
    },
  },

  projectProgress: {
    chartType: "stacked_bar",
    title: "Project Milestone Progress",
    subtitle: "Completion status across active projects",
    echartsOption: {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: ["Completed", "In Progress", "Not Started"] },
      grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
      xAxis: { type: "value" },
      yAxis: {
        type: "category",
        data: ["Project Alpha", "Project Beta", "Project Gamma", "Project Delta", "Project Epsilon"],
      },
      series: [
        { name: "Completed", type: "bar", stack: "total", data: [80, 55, 92, 40, 68], itemStyle: { color: "#c96442" } },
        { name: "In Progress", type: "bar", stack: "total", data: [15, 30, 5, 35, 22], itemStyle: { color: "#d97757" } },
        { name: "Not Started", type: "bar", stack: "total", data: [5, 15, 3, 25, 10], itemStyle: { color: "#e8e6dc" } },
      ],
    },
  },

  recruitmentFunnel: {
    chartType: "funnel",
    title: "Recruitment Funnel",
    subtitle: "Q1 2026 hiring pipeline",
    echartsOption: {
      tooltip: { trigger: "item", formatter: "{b}: {c}" },
      series: [{
        name: "Recruitment",
        type: "funnel",
        left: "10%",
        top: 60,
        bottom: 60,
        width: "80%",
        min: 0,
        max: 100,
        sort: "descending",
        gap: 2,
        label: { show: true, position: "inside" },
        itemStyle: { borderColor: "#faf9f5", borderWidth: 1 },
        data: [
          { value: 100, name: "Applications", itemStyle: { color: "#d1cfc5" } },
          { value: 68, name: "Phone Screen", itemStyle: { color: "#b0aea5" } },
          { value: 42, name: "Technical Interview", itemStyle: { color: "#87867f" } },
          { value: 25, name: "Final Round", itemStyle: { color: "#d97757" } },
          { value: 12, name: "Offer Extended", itemStyle: { color: "#c96442" } },
        ],
      }],
    },
  },

  performanceArea: {
    chartType: "area",
    title: "Team Performance Score Trend",
    subtitle: "Average quarterly performance by team",
    echartsOption: {
      tooltip: { trigger: "axis" },
      legend: { data: ["Engineering", "Product", "Design"] },
      grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
      xAxis: { type: "category", data: ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025", "Q1 2026"] },
      yAxis: { type: "value", name: "Score", min: 60, max: 100 },
      series: [
        {
          name: "Engineering", type: "line", stack: "Total",
          data: [82, 85, 88, 86, 91],
          lineStyle: { color: "#c96442" },
          itemStyle: { color: "#c96442" },
          areaStyle: { opacity: 0.3, color: "rgba(201,100,66,0.15)" },
        },
        {
          name: "Product", type: "line", stack: "Total",
          data: [78, 80, 83, 85, 87],
          lineStyle: { color: "#87867f" },
          itemStyle: { color: "#87867f" },
          areaStyle: { color: "rgba(135,134,127,0.15)" },
        },
        {
          name: "Design", type: "line", stack: "Total",
          data: [85, 88, 90, 87, 92],
          lineStyle: { color: "#d97757" },
          itemStyle: { color: "#d97757" },
          areaStyle: { color: "rgba(217,119,87,0.15)" },
        },
      ],
    },
  },
};

// ─── Mock Chat Sessions ─────────────────────────────────────────────────────

export const MOCK_SESSIONS: ChatSession[] = [
  {
    id: "session-1",
    title: "Q1 Headcount Analysis",
    createdAt: "2026-04-13T09:00:00Z",
    updatedAt: "2026-04-13T09:15:00Z",
    messageCount: 4,
    lastMessage: "Show me headcount by department",
  },
  {
    id: "session-2",
    title: "Turnover Rate Investigation",
    createdAt: "2026-04-12T14:30:00Z",
    updatedAt: "2026-04-12T15:00:00Z",
    messageCount: 6,
    lastMessage: "What's the monthly turnover trend?",
  },
  {
    id: "session-3",
    title: "Compensation Review",
    createdAt: "2026-04-11T10:00:00Z",
    updatedAt: "2026-04-11T10:45:00Z",
    messageCount: 3,
    lastMessage: "Analyze salary distribution",
  },
];

// ─── Mock Messages ──────────────────────────────────────────────────────────

export const MOCK_MESSAGES: Record<string, ChatMessage[]> = {
  "session-1": [
    {
      id: "msg-1a",
      sessionId: "session-1",
      role: "user",
      content: "Show me the current headcount breakdown by department.",
      timestamp: "2026-04-13T09:00:00Z",
    },
    {
      id: "msg-1b",
      sessionId: "session-1",
      role: "assistant",
      content: "Here's the current headcount distribution across all departments. Engineering leads with 156 employees, followed by Sales at 67.",
      chartAsset: {
        assetId: "asset-dept-headcount",
        title: "Headcount by Department",
        chartType: "bar",
      },
      timestamp: "2026-04-13T09:00:30Z",
    },
  ],
  "session-2": [
    {
      id: "msg-2a",
      sessionId: "session-2",
      role: "user",
      content: "What's the monthly employee turnover trend for the past year?",
      timestamp: "2026-04-12T14:30:00Z",
    },
    {
      id: "msg-2b",
      sessionId: "session-2",
      role: "assistant",
      content: "The 12-month rolling turnover shows some seasonal patterns. April and September see peaks, likely due to annual review cycles. The overall trend is declining, which is positive.",
      chartAsset: {
        assetId: "asset-turnover-trend",
        title: "Monthly Turnover Rate",
        chartType: "line",
      },
      timestamp: "2026-04-12T14:31:00Z",
    },
    {
      id: "msg-2c",
      sessionId: "session-2",
      role: "user",
      content: "Can you also show the recruitment pipeline?",
      timestamp: "2026-04-12T14:35:00Z",
    },
    {
      id: "msg-2d",
      sessionId: "session-2",
      role: "assistant",
      content: "Here's the Q1 2026 recruitment funnel. We started with 100 applications and extended 12 offers, giving us a 12% conversion rate. The biggest drop-off is between phone screen and technical interview.",
      chartAsset: {
        assetId: "asset-recruitment-funnel",
        title: "Recruitment Funnel",
        chartType: "funnel",
      },
      timestamp: "2026-04-12T14:36:00Z",
    },
  ],
  "session-3": [
    {
      id: "msg-3a",
      sessionId: "session-3",
      role: "user",
      content: "Show me the salary distribution across the company.",
      timestamp: "2026-04-11T10:00:00Z",
    },
    {
      id: "msg-3b",
      sessionId: "session-3",
      role: "assistant",
      content: "The salary distribution shows a healthy bell curve centered around the ¥25K-40K band. 34% of employees are in the ¥15K-25K range, which is our largest segment.",
      chartAsset: {
        assetId: "asset-salary-dist",
        title: "Salary Band Distribution",
        chartType: "pie",
      },
      timestamp: "2026-04-11T10:01:00Z",
    },
  ],
};

// ─── Mock Chart Assets ──────────────────────────────────────────────────────

export const MOCK_CHART_ASSETS: ChartAsset[] = [
  {
    id: "asset-dept-headcount",
    title: "Headcount by Department",
    description: "Current employee distribution across departments",
    chartType: "bar",
    spec: MOCK_CHART_SPECS.departmentHeadcount,
    sourceMeta: { sessionId: "session-1", messageId: "msg-1b", prompt: "Show me headcount by department" },
    createdAt: "2026-04-13T09:00:30Z",
    updatedAt: "2026-04-13T09:00:30Z",
  },
  {
    id: "asset-turnover-trend",
    title: "Monthly Turnover Rate",
    description: "12-month rolling turnover trend",
    chartType: "line",
    spec: MOCK_CHART_SPECS.turnoverTrend,
    sourceMeta: { sessionId: "session-2", messageId: "msg-2b", prompt: "What's the monthly turnover trend?" },
    createdAt: "2026-04-12T14:31:00Z",
    updatedAt: "2026-04-12T14:31:00Z",
  },
  {
    id: "asset-salary-dist",
    title: "Salary Band Distribution",
    description: "Employee count by compensation tier",
    chartType: "pie",
    spec: MOCK_CHART_SPECS.salaryDistribution,
    sourceMeta: { sessionId: "session-3", messageId: "msg-3b", prompt: "Show salary distribution" },
    createdAt: "2026-04-11T10:01:00Z",
    updatedAt: "2026-04-11T10:01:00Z",
  },
  {
    id: "asset-project-progress",
    title: "Project Milestone Progress",
    description: "Completion status across active projects",
    chartType: "stacked_bar",
    spec: MOCK_CHART_SPECS.projectProgress,
    sourceMeta: { sessionId: "session-1", messageId: "msg-1c", prompt: "Show project progress" },
    createdAt: "2026-04-10T11:00:00Z",
    updatedAt: "2026-04-10T11:00:00Z",
  },
  {
    id: "asset-recruitment-funnel",
    title: "Recruitment Funnel",
    description: "Q1 2026 hiring pipeline",
    chartType: "funnel",
    spec: MOCK_CHART_SPECS.recruitmentFunnel,
    sourceMeta: { sessionId: "session-2", messageId: "msg-2d", prompt: "Show the recruitment pipeline" },
    createdAt: "2026-04-12T14:36:00Z",
    updatedAt: "2026-04-12T14:36:00Z",
  },
  {
    id: "asset-performance-trend",
    title: "Team Performance Score Trend",
    description: "Average quarterly performance by team",
    chartType: "area",
    spec: MOCK_CHART_SPECS.performanceArea,
    sourceMeta: { sessionId: "session-1", messageId: "msg-1d", prompt: "Show team performance trends" },
    createdAt: "2026-04-09T16:00:00Z",
    updatedAt: "2026-04-09T16:00:00Z",
  },
];

// ─── Mock Workspaces ────────────────────────────────────────────────────────

export const MOCK_WORKSPACES: Workspace[] = [
  {
    id: "ws-1",
    title: "Q1 2026 HR Report",
    description: "Quarterly human resources executive summary",
    createdAt: "2026-04-10T08:00:00Z",
    updatedAt: "2026-04-13T09:30:00Z",
    nodeCount: 3,
  },
  {
    id: "ws-2",
    title: "Recruitment Dashboard",
    description: "Ongoing recruitment pipeline metrics",
    createdAt: "2026-04-08T11:00:00Z",
    updatedAt: "2026-04-12T15:00:00Z",
    nodeCount: 2,
  },
];

export const MOCK_WORKSPACE_SNAPSHOTS: Record<string, WorkspaceSnapshot> = {
  "ws-1": {
    workspaceId: "ws-1",
    nodes: [
      {
        id: "node-1",
        type: "chartNode",
        position: { x: 50, y: 50 },
        data: {
          type: "chart",
          assetId: "asset-dept-headcount",
          title: "Headcount by Department",
          chartType: "bar",
          spec: MOCK_CHART_SPECS.departmentHeadcount,
          width: 520,
          height: 380,
        },
      },
      {
        id: "node-2",
        type: "chartNode",
        position: { x: 600, y: 50 },
        data: {
          type: "chart",
          assetId: "asset-turnover-trend",
          title: "Monthly Turnover Rate",
          chartType: "line",
          spec: MOCK_CHART_SPECS.turnoverTrend,
          width: 520,
          height: 380,
        },
      },
      {
        id: "node-3",
        type: "textNode",
        position: { x: 50, y: 460 },
        data: {
          type: "text",
          content: "Q1 2026 Executive Summary: Overall headcount grew 8% YoY while turnover rate decreased to 2.7% in December.",
          width: 1070,
          height: 80,
        },
      },
    ],
    edges: [],
    viewport: { x: 0, y: 0, zoom: 1 },
  },
  "ws-2": {
    workspaceId: "ws-2",
    nodes: [
      {
        id: "node-4",
        type: "chartNode",
        position: { x: 50, y: 50 },
        data: {
          type: "chart",
          assetId: "asset-recruitment-funnel",
          title: "Recruitment Funnel",
          chartType: "funnel",
          spec: MOCK_CHART_SPECS.recruitmentFunnel,
          width: 520,
          height: 400,
        },
      },
      {
        id: "node-5",
        type: "chartNode",
        position: { x: 600, y: 50 },
        data: {
          type: "chart",
          assetId: "asset-salary-dist",
          title: "Salary Band Distribution",
          chartType: "pie",
          spec: MOCK_CHART_SPECS.salaryDistribution,
          width: 520,
          height: 400,
        },
      },
    ],
    edges: [],
    viewport: { x: 0, y: 0, zoom: 1 },
  },
};

// ─── Mock AI Response Generator ─────────────────────────────────────────────

const MOCK_RESPONSES: Array<{ pattern: RegExp; response: AssistantResponse }> = [
  {
    pattern: /headcount|人数|部门/i,
    response: {
      messageId: "",
      content: "Here's the current headcount distribution across all departments. Engineering leads with 156 employees, followed by Sales at 67. The total headcount stands at 409.",
      chartSpec: MOCK_CHART_SPECS.departmentHeadcount,
    },
  },
  {
    pattern: /turnover|离职|流失/i,
    response: {
      messageId: "",
      content: "The 12-month rolling turnover shows seasonal patterns with peaks in April and September, likely due to annual review cycles. The overall trend is declining — December closed at 2.7%, the lowest in the period.",
      chartSpec: MOCK_CHART_SPECS.turnoverTrend,
    },
  },
  {
    pattern: /salary|薪资|compensation|薪酬/i,
    response: {
      messageId: "",
      content: "The salary distribution shows the largest group (128 employees) in the ¥15K-25K band, followed by 96 in ¥25K-40K. The median salary sits around ¥28K. 34 employees are in the >¥60K senior band.",
      chartSpec: MOCK_CHART_SPECS.salaryDistribution,
    },
  },
  {
    pattern: /project|项目|milestone|progress/i,
    response: {
      messageId: "",
      content: "Project Gamma leads with 92% completion, while Project Delta lags at 40%. Overall portfolio health is at 67% average completion. I recommend focusing resources on Delta to meet the Q2 deadline.",
      chartSpec: MOCK_CHART_SPECS.projectProgress,
    },
  },
  {
    pattern: /recruit|招聘|hiring|pipeline/i,
    response: {
      messageId: "",
      content: "The Q1 recruitment funnel shows a 12% overall conversion from application to offer. The largest drop-off is at the technical interview stage — consider reviewing the interview difficulty or process efficiency.",
      chartSpec: MOCK_CHART_SPECS.recruitmentFunnel,
    },
  },
  {
    pattern: /performance|绩效|score|team/i,
    response: {
      messageId: "",
      content: "Team performance scores are trending upward across all three tracked departments. Design leads at 92 in Q1 2026, followed by Engineering at 91. Product is steadily climbing and reached 87.",
      chartSpec: MOCK_CHART_SPECS.performanceArea,
    },
  },
];

const DEFAULT_RESPONSE: AssistantResponse = {
  messageId: "",
  content: "I analyzed the data and here are the key findings. The overall metrics look healthy with some areas for improvement. Would you like me to dig deeper into any specific dimension?",
  chartSpec: MOCK_CHART_SPECS.departmentHeadcount,
};

export function generateMockResponse(prompt: string): AssistantResponse {
  const match = MOCK_RESPONSES.find((r) => r.pattern.test(prompt));
  const base = match?.response ?? DEFAULT_RESPONSE;
  return {
    ...base,
    messageId: `msg-${Date.now()}`,
  };
}
