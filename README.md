# tonys-detailing

Website for **Tony's Detailing** — professional mobile auto detailing based in Chardon, OH.

## Branch Strategy

| Branch | Purpose |
|--------|--------|
| `main` | Live production version — always matches what's deployed on Vercel |
| `dev`  | Working branch for changes before they go live; merge into `main` when ready |
| `v1`   | Snapshot of the original site (Version 1) — never modified |

## Deployment

The site deploys automatically from the `main` branch via Vercel. The entry point is `index.html`.
