import { describe, expect, it } from "vitest";

import {
  buildFallbackSessionTitle,
  DEFAULT_SESSION_TITLE,
  normalizeSessionTitle,
  shouldAutoGenerateSessionTitle,
} from "../../lib/chat/session-title";

describe("session title helpers", () => {
  it("normalizes and limits long titles", () => {
    expect(
      normalizeSessionTitle('  标题：这是一个特别特别特别特别特别长的会话标题，需要被裁剪  ')
    ).toBe("这是一个特别特别特别特别特别长的会话标…");
  });

  it("builds a short fallback title from the first sentence", () => {
    expect(
      buildFallbackSessionTitle("请按部门分析最近 12 个月的离职率变化。并补充关键原因。")
    ).toBe("请按部门分析最近 12 个月的离职率变化");
  });

  it("detects when a brand-new session should request an AI title", () => {
    expect(
      shouldAutoGenerateSessionTitle({
        messageCount: 0,
        title: DEFAULT_SESSION_TITLE,
      })
    ).toBe(true);

    expect(
      shouldAutoGenerateSessionTitle({
        messageCount: 2,
        title: "员工离职趋势分析",
      })
    ).toBe(false);
  });
});
