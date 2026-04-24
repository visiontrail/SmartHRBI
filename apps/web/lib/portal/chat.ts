export type PortalChatEventType = "planning" | "tool_use" | "tool_result" | "final" | "error";

export type PortalChatEvent = {
  type: PortalChatEventType;
  payload: Record<string, unknown>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function sendPortalChatMessage(
  pageId: string,
  message: string,
  options: { chartId?: string | null } = {}
): Promise<PortalChatEvent[]> {
  const response = await fetch(`${API_BASE_URL}/portal/pages/${encodeURIComponent(pageId)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      chart_id: options.chartId || undefined,
    }),
  });
  const text = await response.text();
  if (!response.ok) throw new Error("Portal chat failed");
  return parseSse(text);
}

export function parseSse(raw: string): PortalChatEvent[] {
  return raw
    .split(/\n\n+/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const eventLine = block.split("\n").find((line) => line.startsWith("event:"));
      const dataLine = block.split("\n").find((line) => line.startsWith("data:"));
      const type = (eventLine?.replace(/^event:\s*/, "") || "final") as PortalChatEventType;
      let payload: Record<string, unknown> = {};
      if (dataLine) {
        try {
          const parsed = JSON.parse(dataLine.replace(/^data:\s*/, ""));
          if (parsed && typeof parsed === "object") payload = parsed;
        } catch {
          payload = {};
        }
      }
      return { type, payload };
    });
}
