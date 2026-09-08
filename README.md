# ChargeWatch

ChargeWatch checks ZSE Drive stations `73151` and `72182` every minute and
stores one snapshot per connector in Convex.

Each snapshot contains the station ID, connector ID, EVSE ID, normalized and
raw state, check time, station name, and address.

## Convex backend

Install dependencies and connect a development deployment:

```bash
npm install
npx convex dev --once
```

The one-minute schedule is defined in `convex/crons.ts`. It invokes the
collector action, which fetches both stations in parallel and writes successful
responses in one mutation.

Run and inspect the collector manually:

```bash
npx convex run stations:collect '{}'
npx convex run stations:latest '{}'
npx convex run stations:history '{"stationId":73151,"limit":100}'
```

The public `stations:latest` and `stations:history` queries are ready for a
React or Next.js frontend using Convex subscriptions.

Deploy the backend to production only after verifying the development
deployment:

```bash
npx convex deploy
```

`.env.local` identifies the linked local deployment and must not be committed.

## Local Python utility

The original Python monitor remains available for local Excel or SQLite export:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python monitor.py --once --excel connector_availability.xlsx
```