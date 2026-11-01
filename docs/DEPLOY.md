# Deploying 1Finance publicly (with Google sign-in)

The whole stack runs on a single small Linux server with Docker Compose. Caddy sits in front and obtains HTTPS
certificates automatically. Anyone can open the site and sign up / sign in with their Google account; each
account only ever sees its own data.

```
Internet ──443──▶ Caddy ──/api/*──▶ api (FastAPI) ──▶ Postgres
                        └──────────▶ web (Next.js)     worker (Celery) ──▶ Redis
```

## What you need

| Item | Notes | Typical cost |
|---|---|---|
| A Linux server (VPS) | Ubuntu 24.04, **2 GB RAM or more** (the web build needs it). E.g. Hetzner CX22, DigitalOcean 2 GB droplet | ~€4–12 / month |
| A domain name | Any registrar (Cloudflare, Namecheap, …). Google sign-in needs a real domain over HTTPS | ~€10 / year |
| A Google Cloud project | Free | — |

## 1. Point your domain at the server

Create the server, note its public IPv4 address, and add a DNS record at your registrar:

| Type | Name | Value |
|---|---|---|
| A | `1finance` (or `@` for the bare domain) | your server's IP |

## 2. Create the Google OAuth client

In [Google Cloud Console](https://console.cloud.google.com/):

1. Create (or pick) a project.
2. **Google Auth Platform → Branding** (older consoles: *APIs & Services → OAuth consent screen*):
   app name, user support email, developer contact email. Under **Authorized domains** add your domain
   (e.g. `example.com`). Add links to your home page and a privacy policy page.
3. **Audience**: user type **External**. Click **Publish app** so it is *In production*. While it is in
   *Testing*, only the test users you list can sign in.
4. **Data access**: the scopes 1Finance asks for are `openid`, `email` and `profile`. These are non-sensitive, so
   Google does not require an app review.
5. **Clients → Create client → Web application**:
   - Authorized JavaScript origins: `https://YOUR_DOMAIN`
   - Authorized redirect URIs: `https://YOUR_DOMAIN/api/v1/auth/google/callback`
   - (optional, for local testing) also add `http://localhost:3000/api/v1/auth/google/callback`
6. Copy the **Client ID** and **Client secret**.

## 3. Prepare the server

```bash
ssh root@YOUR_SERVER_IP

# Docker
curl -fsSL https://get.docker.com | sh

# Firewall: SSH + HTTP(S) only
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable

# Code (for a private repo, use a deploy key or `gh auth login` first)
git clone https://github.com/balajisivakumar-20/1finance.git && cd 1finance
```

## 4. Configure

```bash
cp .env.production.example .env.production
openssl rand -base64 24   # → POSTGRES_PASSWORD
openssl rand -base64 32   # → CREDENTIAL_KEY
nano .env.production      # set DOMAIN, the two values above, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
```

Keep a copy of `.env.production` (especially `CREDENTIAL_KEY`) in a password manager.

## 5. Start it

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f api caddy   # watch the first start
```

The API runs database migrations and loads reference data on every start. Production never loads demo data.
Open `https://YOUR_DOMAIN` and click **Continue with Google**.
The first sign-in creates the account. Later sign-ins with the same Google account log into it.

## Updating

```bash
cd 1finance && git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

## Backups

```bash
# daily database dump at 03:00, keep 14 days
mkdir -p /root/backups
crontab -e
0 3 * * * cd /root/1finance && docker compose -f docker-compose.prod.yml --env-file .env.production exec -T db pg_dump -U onefinance onefinance | gzip > /root/backups/1finance-$(date +\%F).sql.gz && find /root/backups -name '*.sql.gz' -mtime +14 -delete
```

Copy backups off the server too (e.g. to object storage). Test restoring a backup at least once.

## How Google sign-in works

- `GET /api/v1/auth/google/start` redirects to Google using the authorization-code flow with PKCE. The `state`,
  `nonce` and PKCE verifier are kept in a short-lived encrypted cookie.
- Google redirects back to `/api/v1/auth/google/callback`. The API exchanges the code for an ID token and
  checks its issuer, audience, expiry and nonce. It also requires the Google email address to be verified.
- The account is matched by its Google ID. If no account has that ID but one exists with the same verified email,
  the Google account is linked to it. Otherwise a new account is created.
- If the user has turned on two-factor codes (Settings → Security), they must still enter their 6-digit code
  after Google before a session is created.
- When Google sign-in is configured and demo mode is off, the login page shows only **Continue with Google**.

## Before inviting other people

You will be storing other people's financial data. At a minimum:

- Publish a privacy policy and terms page. Google's consent screen also asks for them.
- Keep the server patched (`apt upgrade`) and keep backups encrypted and off-site.
- Rate limiting is in-process, which is fine for this single-server setup. Move it to Redis if you run more than
  one API container.
