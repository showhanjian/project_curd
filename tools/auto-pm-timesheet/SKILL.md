---
name: auto-pm-timesheet
description: 自动登录 Git 项目管理平台（pm.git.com.cn）填写并提交"我的工时"。当用户要求按指定日期、项目、任务、工时、描述自动填工时、或提到"自动填工时"/"自动化工时"/"PM 工时"时触发。在 Codex 内置 iab 浏览器里执行；登录密码走环境变量 PM_PASSWORD，绝不落盘明文。
---

# auto-pm-timesheet

按以下顺序在 Codex iab 浏览器里执行。每一步前都先 `let tab = await cua.getTab("1", { browser: "iab" })` 重新绑定；所有 `tab.playwright.xxx` 必须 `try/catch`，避免异步 reject 触发内核重置。

详细选择器见 `references/selectors.md`，调用入口见 `scripts/run.js`。

## 1. 复用登录会话（推荐）

如果 iab 浏览器已经手动登录过 `pm.git.com.cn`，直接跳到步骤 2。如果还没登录：

```js
await tab.playwright.goto("http://pm.git.com.cn/Employee/Default.aspx");
await tab.playwright.waitForTimeout(1500);
if (!tab.playwright.url().includes("Default.aspx")) {
  await tab.playwright.locator('input[name*="user" i], input[id*="user" i]').first().fill(process.env.PM_USER);
  await tab.playwright.locator('input[type="password"]').first().fill(process.env.PM_PASSWORD);
  await tab.playwright.locator('input[type="submit"], button:has-text("登录")').first().click();
  await tab.playwright.waitForTimeout(2500);
}
```

## 2. 进入"我的工时"

URL 直达：`http://pm.git.com.cn/Employee/AccountEmployeeTimeEntryDayView.aspx?StartDate=<date>`

URL 不可达时回退菜单：左侧菜单 → 我的工时 → 填日期 → 点检索。

## 3. 填 row

GridView 行号后缀：`ctl02`（row 0）、`ctl04`（row 1）、`ctl05`（row 2）……

字段 ID 前缀：`#ctl00_ctl00_ctl00_CB_CB_ContentPlaceHolderBody_CtlAccountEmployeeTimeEntryDayView1_BulkEditGridViewVB1_<rowId>_`

操作顺序（重要）：

1. 选项目 → **等 800ms**（任务下拉异步回填）
2. 选任务
3. 选工作类型
4. 工时显示框 `TotalTime` 填 `08:00`，隐藏框 `Hours` 和 `Hours2` 都填 `8`
5. `SubRemark` 填工作描述

## 4. 保存 + 提交

```js
tab.playwright.on("dialog", d => d.accept());
await tab.playwright.locator("#ctl00_ctl00_ctl00_CB_CB_ContentPlaceHolderBody_CtlAccountEmployeeTimeEntryDayView1_btnSave").click();
await tab.playwright.waitForTimeout(2000);
await tab.playwright.locator("#ctl00_ctl00_ctl00_CB_CB_ContentPlaceHolderBody_CtlAccountEmployeeTimeEntryDayView1_btnSubmit").click();
await tab.playwright.waitForTimeout(2000);
```

## 5. 校验 + 截图

读 `imgStatus` 的 `alt`，期望 `已提交`。截图存到 `timesheet-<date>.png`。

## 调用入口

```js
const { run } = await import("D:/My_play/project_curd/tools/auto-pm-timesheet/scripts/run.js");
await run({
  date: "2026-10-08",
  project: "湖北建行 风险预警平台项目二期",
  task: "文档整理",
  hours: 8,
  description: "写文档"
});
```

## 输入参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `date` | 是 | YYYY-MM-DD |
| `project` | 是 | 项目全称（精确匹配 select label） |
| `task` | 是 | 任务全称 |
| `hours` | 是 | 整数 |
| `description` | 是 | 工作描述 |
| `work_type` | 否 | 默认 `本地` |

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `PM_USER` | 推荐 | 登录用户名 |
| `PM_PASSWORD` | 必填 | 登录密码，**绝不落盘** |

## 异常分支

| 现象 | 处理 |
|---|---|
| 登录失败 / 验证码 | 截图 + 读 `lblMessage` 文字报错退出 |
| row 状态已是 `已提交` | 跳过或提示用户删除该行 |
| 任务下拉为空 | 项目切换后等 800ms 再选；仍空则触发 change 事件 |
| 保存按钮 disabled | 读页面红色错误提示 |
| `cua_repl` 报 `missing field code` | 内核重置，从头初始化会话 |
| 项目下拉找不到 | 列全部 option label 给用户确认名称 |

## 安全

- skill 文件里**绝不出现**明文密码
- 密码只走 `PM_PASSWORD` 环境变量
- 截图存到用户 home 目录，不进任何 git 仓库
