# ZSE Drive connector monitor

The monitor checks stations `73151` and `72182` every five minutes and appends
one row per connector to `connector_availability.xlsx`.

The workbook contains:

- `station_id`
- `connector_id`
- `evse_id`
- `state` (`available`, `unavailable`, or the API's unrecognized state)
- `checked_at` (local time with UTC offset)
- `name`
- `address`

## Setup

```bash
cd /Users/ms639x/Projects/adam_charger
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run continuously, checking every 300 seconds:

```bash
.venv/bin/python monitor.py
```

Keep that process running. Stop it with `Ctrl+C`.

To verify a single check without starting the loop:

```bash
.venv/bin/python monitor.py --once
```

Custom stations or interval can be supplied when needed:

```bash
.venv/bin/python monitor.py --stations 73151 72182 --interval 300
```

Run a bounded high-frequency capture and write all buffered samples at the end:

```bash
.venv/bin/python monitor.py --interval 0.1 --duration 5 --timeout 1
```

The interval is a target. Sampling cannot be faster than the API response time.

Do not keep the Excel workbook open while the script writes to it. Excel may
lock the file and cause that check to fail.