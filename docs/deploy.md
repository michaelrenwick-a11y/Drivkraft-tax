# Deploying the demo

Two pieces: the Python server (API + MCP + OpenTax) as a container on Fly.io, and the
web app on Vercel. The web proxies `/api` to the server, so the browser sees one origin
and the visitor cookie works without CORS.

## 1. Server on Fly.io

```bash
brew install flyctl          # or: curl -L https://fly.io/install.sh | sh
fly auth login
fly launch --no-deploy --copy-config          # keeps fly.toml; rename the app if taken
fly volumes create drivkraft_data --size 1 --region ord
fly secrets set DRIVKRAFT_INVITE_CODE="$(openssl rand -hex 12)"
fly secrets set ANTHROPIC_API_KEY=sk-ant-...  # optional: chat + meeting analysis, capped by DRIVKRAFT_MONTHLY_CAP_USD
fly secrets set BIZORA_API_KEY=...            # optional: live research (invite code required)
fly deploy
curl https://<app>.fly.dev/api/demo           # {"demo": true, ...}
```

If the app name isn't `drivkraft-tax`, update `DRIVKRAFT_PUBLIC_HOSTS` in `fly.toml`. It's the
Host header that `/mcp` accepts.

The image runs `scripts/bootstrap.sh`, which clones the pinned otd-spec and OpenTax and
downloads the `opentax-linux-x64` release binary. Keep one machine: SQLite lives on the
volume, and the rate limits and sandbox pool are in memory.

## 2. Web on Vercel

```bash
cd web
vercel link                  # new project, root directory: web
vercel env add DRIVKRAFT_API production    # https://<app>.fly.dev
vercel --prod
```

`next.config.ts` reads `DRIVKRAFT_API` at build time for the `/api` rewrite, so redeploy after
changing it.

## 3. Check it

- A fresh private window lands on Cases with the demo banner, and the tour opens on its own.
  You should see three sandbox cases plus two reference cases.
- A second private window has different sandbox case ids.
- `/operator` → Demo visitors shows the counts, the sandboxes ready and this month's AI spend against the cap.
- `curl -X POST https://<app>.fly.dev/mcp` returns 401. With the invite code as the bearer token,
  `claude mcp add --transport http …` connects.

## Before sharing the link

- Run one live chat turn and one live `analyze_meeting` with the real key. Then check that
  `/operator` logs the usage rows.
- Have the three cached research answers (`server/research_cache.yaml`) and the cached Rivera
  analysis (`server/notes_samples.yaml`) read against their authorities. They're authored, not
  Bizora output.
- Make one real Bizora call to confirm the streamed `custom_data` source placement the parser assumes.
