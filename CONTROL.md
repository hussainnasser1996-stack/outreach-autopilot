# Outreach autopilot — control (edit from phone via GitHub app, or tell Claude)

mode: auto
daily_cap: 120
send_days: Sun,Mon,Tue,Wed,Thu
uae_send_days: Mon,Tue,Wed,Thu,Fri
followups: on
followup_days: 7
approved_batches: [G2, G3, I1, I2, I3, I4, I5]

## How approval works
- New firms land in `pending/` as a batch (e.g. G1). Each batch is shown to Hussain (firm, person, role, address, hook).
- Only batches listed in `approved_batches` are ever sent. Add the batch id once he says OK.
- `mode: paused` stops everything (sends and follow-ups). Replies still reach Gmail as normal.
- Every run pushes a summary to the ntfy app; a real reply pushes a high-priority alert.
