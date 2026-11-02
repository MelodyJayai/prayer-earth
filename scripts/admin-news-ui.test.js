import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";

function loadPublishVerifiedUi() {
  const html = readFileSync("scripts/admin.html", "utf8");
  const matched = html.match(/\/\* publish-verified-ui \*\/([\s\S]*?)\/\* \/publish-verified-ui \*\//);
  if (!matched) {
    throw new Error("admin.html 缺少 publish-verified-ui");
  }
  const sandbox = {};
  runInNewContext(
    `${matched[1]}
this.exports = { countPublishableNews, publishVerifiedConfirmText, publishVerifiedButtonState, publishVerifiedDecision };`,
    sandbox,
  );
  if (!sandbox.exports) {
    throw new Error("未能加载一键公开确认逻辑");
  }
  return { html, ...sandbox.exports };
}

describe("一键公开已核实确认", () => {
  const ui = loadPublishVerifiedUi();

  it("只把待审且 verified 为布尔真的条目算进确认条数", () => {
    const count = ui.countPublishableNews([
      { id: "a", status: "pending", verified: true },
      { id: "b", status: "pending", verified: false },
      { id: "c", status: "pending", verified: "false" },
      { id: "d", status: "pending", verified: "true" },
      { id: "e", status: "pending", verified: 1 },
      { id: "f", status: "pending" },
      { id: "g", status: "published", verified: true },
      { id: "h", status: "rejected", verified: true },
      null,
    ]);
    expect(count).toBe(1);
  });

  it("确认文案带上服务端条数，条数为 0 时不进入提交", () => {
    expect(ui.publishVerifiedConfirmText(51)).toContain("51");
    expect(ui.publishVerifiedConfirmText(51)).toContain("备用站");
    expect(ui.publishVerifiedDecision(0, true)).toEqual({ action: "empty", expectedCount: 0 });
    expect(ui.publishVerifiedDecision(51, false)).toEqual({ action: "cancel", expectedCount: 51 });
    expect(ui.publishVerifiedDecision(51, true)).toEqual({ action: "post", expectedCount: 51 });
  });

  it("没有可公开条目时禁用按钮，有条目时在按钮上显示条数", () => {
    expect(ui.publishVerifiedButtonState(0)).toEqual({
      disabled: true,
      label: "一键公开已核实",
      title: "没有已核实的待审动态",
    });
    expect(ui.publishVerifiedButtonState(51)).toEqual({
      disabled: false,
      label: "一键公开已核实（51）",
      title: "公开 51 条已核实的待审动态",
    });
  });

  it("页面按钮会把确认后的条数交给批量接口", () => {
    expect(ui.html).toContain('id="publish-verified"');
    expect(ui.html).toContain("publishVerifiedDecision");
    expect(ui.html).toContain("/news/publish-verified");
    expect(ui.html).toContain("expected_count");
  });
});
