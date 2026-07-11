# Security Policy

## Overview

StudySuite AI runs entirely on the user's machine. This document describes exactly
what data the app touches, what leaves the device, what third-party code runs, and
why — so anyone can verify these claims by reading the source rather than trusting
a description of it.

If any part of the implementation drifts from what's written here, that's a bug.
Open an issue.

---

## Data Handling

### What is stored locally

| Data | Location | Encrypted at rest | Ever transmitted by this app |
|---|---|---|---|
| Google OAuth token (YouTube readonly) | `~/.studysuite/yt_token.pickle` | No (relies on OS filesystem permissions) | Only to `googleapis.com`, directly by the user's OAuth session |
| Video transcripts / notes | `~/StudySuite/Output/` | No | No |
| App settings | `~/.studysuite/config.json` | No | No |

### What is never stored or touched

- **Browser cookies** — this app does not read browser cookie databases
  (`cookiesfrombrowser`) and does not accept cookie file imports (`cookies.txt`).
  No YouTube session credential of any kind is ever read, stored, or handled by
  this application.
- **Passwords** — the app never asks for or handles a Google password. All
  authentication happens on Google's own consent screen via OAuth; this app
  never sees the credential, only the token Google issues after the user
  explicitly clicks "Allow."
- **User activity logs** — there is no telemetry, no analytics, and no relay
  server. No record of which videos a user processes leaves their machine.

---

## Authentication Model

### Metadata & chapters — Google OAuth 2.0

- Flow: `InstalledAppFlow.run_local_server` (standard desktop OAuth flow)
- Scope requested: `youtube.readonly` only — no write, no upload, no account
  management access
- Token is revocable at any time by the user via
  [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
- This app never sees the user's Google password. The token grants access only
  to the scope above and only to the YouTube Data API v3.

**Why this is the trust boundary of the app:** this is the only credentialed
path in the pipeline, and it is entirely delegated to Google's own
infrastructure and consent UI. There is no custom auth code to audit here —
only standard, widely-used OAuth libraries.

### Transcripts — no credentials involved

Transcript extraction uses `yt-dlp` with a bundled Proof-of-Origin (PO) Token
provider. This mechanism:

- Does **not** use any user account, password, or session cookie
- Generates a synthetic attestation token, unrelated to any individual identity
- Runs as a local subprocess with no network access beyond YouTube's public
  endpoints

**Consequence of this design:** if transcript extraction fails, the failure is
visible and safe — a missing transcript, not an exposed account. There is no
credential in this path that could leak, expire insecurely, or be misused.

---

## Third-Party Code Disclosure

| Component | Purpose | Trust surface |
|---|---|---|
| `yt-dlp` | Video metadata/subtitle extraction | Widely audited, pinned exact version |
| `bgutil-ytdlp-pot-provider` | Generates PO Tokens locally via a subprocess | Runs local code with system privileges; version-pinned, built from source at install time, not pulled as a prebuilt binary |
| `google-auth-oauthlib` | OAuth flow | Official Google library |
| `google-api-python-client` | YouTube Data API v3 calls | Official Google library |

All dependency versions are pinned in `requirements.txt`. Automatic updates of
security-relevant components (the PO Token provider in particular) are
disabled by default — updates require an explicit version bump and changelog
entry in a release, not a silent `pip install -U` at runtime.

---

## Explicit Non-Goals

To be direct about what this app deliberately does **not** do, because these
are common patterns in similar tools that we've chosen to avoid:

- ❌ No reading of browser cookie databases
- ❌ No cookies.txt import
- ❌ No relay/proxy server that routes user requests through our infrastructure
- ❌ No telemetry or usage analytics by default
- ❌ No auto-updating of the PO Token provider without user-visible release notes

---

## Known Limitations (Not Vulnerabilities)

- Transcript extraction is best-effort. YouTube's anti-bot measures change
  over time, and no scraping-based method (including this one) can guarantee
  100% availability. When it fails, the app fails visibly — it does not
  silently retry with a more invasive method.
- The OAuth-based metadata path cannot retrieve transcripts for videos the
  authenticated user does not own — this is a restriction of the YouTube Data
  API itself, not a limitation we can lift.

---

## Reporting a Vulnerability

If you find a security issue — including any behavior that contradicts what's
described in this document — please report it privately rather than opening a
public issue:

- Email: `security@[yourdomain]` *(replace before publishing)*
- Please include: reproduction steps, affected version, and impact assessment
- We aim to acknowledge reports within 72 hours

Do not include exploit details in public GitHub issues.

---

## Verifying This Document Yourself

Because this project is open source, every claim above is checkable:

- Search the codebase for any network call to confirm nothing transmits
  outside `googleapis.com` and YouTube's own endpoints.
- Search for `cookiesfrombrowser` and `cookies.txt` — both should return zero
  matches.
- Check `requirements.txt` for pinned (not floating) versions of
  `yt-dlp` and `bgutil-ytdlp-pot-provider`.

If any of this doesn't hold, treat it as a bug and report it.
