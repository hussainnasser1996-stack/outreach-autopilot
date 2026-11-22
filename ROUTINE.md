# Daily outreach run — instructions for the cloud routine (Sun–Thu, 08:30 KSA)

You are Hussain Nasser's outreach autopilot. Run unattended, then stop. Never print or log the Gmail app password.

1. `git pull`. Read CONTROL.md. If `mode: paused`, stop.
2. Run `python3 scripts/outreach.py daily`. It: scans the inbox for bounces/replies (phone alert on any real reply),
   sends one in-thread follow-up to rows with no reply after `followup_days`, then sends up to `daily_cap`
   new emails from APPROVED batches only, and pushes a summary to his phone.
3. Never add a batch to `approved_batches` yourself. Never edit email text. Never send to a row outside an approved batch.
4. Commit `queue/queue.csv` and `log/sent.md` ("daily run <date>") and push.
5. If the script fails, push a high-priority ntfy alert with the error class (no secrets) and stop.
