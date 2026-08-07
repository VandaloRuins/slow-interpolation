---
updated: YYYY-MM-DD
last_sweep: YYYY-MM-DDTHH:MM
schema_version: 1
---

# Priorities

<!--
Starting scaffold for the file /todo owns (config.paths.priorities_file).
Replace the section headings below with YOUR config.buckets labels. The row columns and the
standing sections (Fire / Watching / Dormant / Completed / Archive) stay as-is.

Row columns:
| id | item | objective | desired_result | next_move | due | escalation | status | channel | thread |
  status:  DRAFT / SENT / WAITING / OBSTACLE / DONE / DEFERRED
  channel: email / chat / call / internal / multi
  thread:  path to the thread file or interaction log, or --
-->

## Fire (next 48h)
<!-- Regenerated at the end of each `/todo full` sweep (overdue + awaiting-past-escalation +
     due-soon). Do not hand-maintain; it is regenerated, not edited. -->

## <Bucket 1 label — e.g. Pre-Launch>
### <Section name>
| id | item | objective | desired_result | next_move | due | escalation | status | channel | thread |
|----|------|-----------|----------------|-----------|-----|-----------|--------|---------|--------|

## <Bucket 2 label — e.g. Live Events>
### <Section name>

## <Bucket 3 label — e.g. Post-Launch>
### <Section name>

## <Bucket 4 label — e.g. Standing>
### <Section name>

## Watching (sent, awaiting replies)
<!-- same row schema as the buckets -->

## Dormant (paused, door open)

## Completed — last 30 days
<!-- rolling window, prose OK. Items older than 30 days move to the Archive. -->

## Archive
- [YYYY-Qn](priorities-archive/YYYY-Qn.md)