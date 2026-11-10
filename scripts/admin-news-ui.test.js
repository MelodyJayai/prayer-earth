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
this.exports = { countPublishableNews, publishVerifiedConfirmText, publishVerifiedButtonState, publishVerifiedDecision, publishVerifiedButtonVisible };`,
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

  it("一键公开按钮默认隐藏，只有服务端布尔真才显示", () => {
    expect(ui.publishVerifiedButtonVisible(true)).toBe(true);
    expect(ui.publishVerifiedButtonVisible(false)).toBe(false);
    expect(ui.publishVerifiedButtonVisible(undefined)).toBe(false);
    expect(ui.publishVerifiedButtonVisible("true")).toBe(false);
    expect(ui.publishVerifiedButtonVisible(1)).toBe(false);
    expect(ui.html).toMatch(/id="publish-verified"[^>]*\shidden\b/);
    expect(ui.html).toContain("showPublishVerified");
  });
});

function loadNewsReviewUi() {
  const html = readFileSync("scripts/admin.html", "utf8");
  const matched = html.match(/\/\* news-review-ui \*\/([\s\S]*?)\/\* \/news-review-ui \*\//);
  if (!matched) throw new Error("admin.html 缺少 news-review-ui");
  const sandbox = {};
  runInNewContext(
    `${matched[1]}\nthis.exports = { newsReviewActionLabel, newsReviewConfirmText, newsReviewSuccessText };`,
    sandbox,
  );
  return { html, ...sandbox.exports };
}

describe("逐条撤下已公开动态", () => {
  const ui = loadNewsReviewUi();

  it("已公开显示撤下，待审显示驳回，已驳回不再提供撤下", () => {
    expect(ui.newsReviewActionLabel("published")).toBe("撤下");
    expect(ui.newsReviewActionLabel("pending")).toBe("驳回");
    expect(ui.newsReviewActionLabel("rejected")).toBe("");
    expect(ui.newsReviewConfirmText("published", "reject")).toContain("内容版本加 1");
    expect(ui.newsReviewConfirmText("pending", "reject")).toContain("驳回");
    expect(ui.newsReviewSuccessText("published", "reject")).toBe("动态已撤下。");
    expect(ui.html).toContain("newsReviewActionLabel");
    expect(ui.html).toContain("return '撤下'");
  });
});

function loadPrayerFilterUi() {
  const html = readFileSync("scripts/admin.html", "utf8");
  const matched = html.match(/\/\* prayer-filter-ui \*\/([\s\S]*?)\/\* \/prayer-filter-ui \*\//);
  if (!matched) throw new Error("admin.html 缺少 prayer-filter-ui");
  const sandbox = {};
  runInNewContext(`${matched[1]}\nthis.exports = { prayerFilterVisible, prayerFilterAction };`, sandbox);
  return { html, ...sandbox.exports };
}

describe("迫害筛选", () => {
  const ui = loadPrayerFilterUi();

  it("只把待审和已公开放进筛选，并按排除、自动放行、手动标记决定按钮", () => {
    expect(ui.prayerFilterVisible({ status: "pending" })).toBe(true);
    expect(ui.prayerFilterVisible({ status: "published" })).toBe(true);
    expect(ui.prayerFilterVisible({ status: "rejected" })).toBe(false);
    const auto = { status: "published", verified: true, prayerCandidate: true, onPrayerPage: true, needsPrayer: false, prayerExcluded: false };
    expect(ui.prayerFilterAction(auto)).toBe("exclude");
    expect(ui.prayerFilterAction({ ...auto, prayerExcluded: true, onPrayerPage: false })).toBe("unexclude");
    expect(ui.prayerFilterAction({ status: "published", verified: false, prayerCandidate: true, onPrayerPage: false, needsPrayer: false })).toBe("mark");
    expect(ui.prayerFilterAction({ status: "published", verified: false, prayerCandidate: true, onPrayerPage: true, needsPrayer: true })).toBe("unmark");
  });

  it("页面提供设为需要祷告、取消和排除", () => {
    expect(ui.html).toContain('id="tab-prayer-filter"');
    expect(ui.html).toContain("设为需要祷告");
    expect(ui.html).toContain("/prayer-exclusion");
    expect(ui.html).toContain("needs_prayer");
  });
});
