"""Audit 0.10: delay between a cron's nominal time and the run's created_at."""
import datetime as dt
import json
import statistics
from pathlib import Path

d = json.loads((Path(__file__).resolve().parents[2] / "docs/evidence/gha_schedule_runs.json").read_text())
all_delays = []
for wf, v in d["workflows"].items():
    minute, hour = (int(x) for x in v["cron"].split()[:2])
    delays = []
    for c in v["created_at"]:
        t = dt.datetime.fromisoformat(c.replace("Z", "+00:00"))
        nominal = t.replace(hour=hour, minute=minute, second=0)
        delays.append((t - nominal).total_seconds() / 60)
    all_delays += delays
    print(f"{wf:13s} cron={v['cron']:12s} n={len(delays):2d} delay min: "
          f"min={min(delays):.0f} median={statistics.median(delays):.0f} max={max(delays):.0f}")
print(f"ALL n={len(all_delays)} min={min(all_delays):.0f} median={statistics.median(all_delays):.0f} "
      f"max={max(all_delays):.0f} (minutes)")
