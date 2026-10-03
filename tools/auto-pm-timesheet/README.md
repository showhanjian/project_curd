# auto-pm-timesheet

Auto-fill the Git PM system My Timesheet page in the Codex iab browser.

## Install

Drop this folder into `D:/My_play/project_curd/tools/auto-pm-timesheet/` and commit it.

## Config

PowerShell:
```
$env:PM_USER = "hanjian@git.com.cn"
$env:PM_PASSWORD = "your password"
```

Or log into `http://pm.git.com.cn` once in the iab browser and let the skill reuse the session.

## Call

```
const { run } = await import("D:/My_play/project_curd/tools/auto-pm-timesheet/scripts/run.js");
await run({
  date: "2026-10-08",
  project: "Hubei JianHang Risk Warning Platform Phase 2",
  task: "Docs",
  hours: 8,
  description: "write docs"
});
```

## Safety

The password lives only in `PM_PASSWORD`. This skill file contains no plaintext credentials and is safe to commit.
