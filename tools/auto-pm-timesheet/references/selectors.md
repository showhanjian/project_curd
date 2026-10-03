# Selectors cheatsheet

## GridView row id rule

| Row | rowId |
|-----|-------|
| 0   | ctl02 |
| 1   | ctl04 |
| 2   | ctl05 |
| n>=4| ctl0{n+3} |

Verify against the actual page source tr id suffix.

## Field ids

Prefix: `ctl00_ctl00_ctl00_CB_CB_ContentPlaceHolderBody_CtlAccountEmployeeTimeEntryDayView1`

| Field | Full id |
|-------|---------|
| Date | `..._txtTimeEntryDate` |
| Search | `..._btnShow` |
| Save | `..._btnSave` |
| Submit | `..._btnSubmit` |
| Project | `..._BulkEditGridViewVB1_<rowId>_ddlAccountProjectId` |
| Task | `..._BulkEditGridViewVB1_<rowId>_ddlAccountProjectTaskId` |
| Work type | `..._BulkEditGridViewVB1_<rowId>_ddlAccountWorkTypeId` |
| Hours display | `..._BulkEditGridViewVB1_<rowId>_TotalTime` |
| Hours hidden | `..._BulkEditGridViewVB1_<rowId>_Hours` and `_Hours2` |
| Description | `..._BulkEditGridViewVB1_<rowId>_SubRemark` |
| Status icon | `..._BulkEditGridViewVB1_<rowId>_imgStatus` |
| Delete | `..._BulkEditGridViewVB1_<rowId>_btnDelete` |

## Menu fallback

- Left menu: My Timesheet
- Top: Home -> My Timesheet
