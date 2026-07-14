# Engineering Rules — YouTube Extraction Pipeline

These rules govern how this repo handles YouTube data extraction. They exist
because it's easy for "just add cookie support, it's more reliable" to creep
back into the codebase over time. Read this before touching anything in
`pipeline/`, `auth/`, or `extraction/`.

---

## 1. Non-negotiables

These are hard rules, not preferences. A PR that violates any of these should
be rejected regardless of how much more reliable it makes extraction.

1. **No cookie handling of any kind.**
   No `cookiesfrombrowser`, no `cookies.txt` import, no reading of any
   browser's local storage or cookie database. If a dependency update
   silently re-enables this by default, it must be explicitly disabled in
   our config.

2. **No relay/proxy infrastructure.**
   All extraction happens locally, on the user's machine. Do not add a
   backend service that fetches videos on the user's behalf, even as an
   opt-in "faster mode." This is a permanent architectural constraint, not a
   v1 limitation.

3. **No credential ever touches disk unencrypted-and-unnecessary.**
   The only credential in this app is the OAuth token, and it is scoped to
   `youtube.readonly`. Do not request broader scopes without updating
   `SECURITY.md` and calling it out explicitly in the PR description.

4. **No silent escalation on failure.**
   If a lower-trust extraction method fails, the pipeline must surface a
   visible error or degraded state — it must never automatically fall back to
   a more invasive method (e.g., prompting for cookies) without the user
   consciously opting in.

5. **No floating dependency versions for extraction-critical packages.**
   `yt-dlp` and `bgutil-ytdlp-pot-provider` must be pinned to exact versions
   in `requirements.txt`. Version bumps require a changelog entry.

---

## 2. Extraction Pipeline Order

The pipeline must attempt extraction in this order and no other:

```
1. Metadata + chapters → Google OAuth (YouTube Data API v3)
2. Transcript → yt-dlp + bundled PO Token provider
3. On failure → visible error state, offer manual retry
```

There is no step 4. Do not add a cookie-based fallback as "step 4," even
labeled as opt-in advanced/power-user mode. If this constraint is ever
revisited, it requires a design discussion and an update to both this file
and `SECURITY.md`, not a quiet PR.

---

## 3. OAuth Rules

- Scope must remain `youtube.readonly` unless a documented feature requires
  more, approved via issue discussion first.
- Token storage: local file only (`~/.studysuite/yt_token.pickle` or
  equivalent). Never log the token, never include it in crash reports or
  error telemetry.
- Token refresh must happen silently in the background; expired/revoked
  tokens must degrade to "Connect your YouTube" UI state, not a crash.

---

## 4. Third-Party Extraction Code

- `bgutil-ytdlp-pot-provider` (or any PO Token provider) must be:
  - Built from source at install time where feasible, not pulled as an
    opaque prebuilt binary.
  - Pinned to an exact version/commit.
  - Documented in `SECURITY.md` with what it does and why it's trusted.
- Do not add additional third-party extraction/bypass tools without the same
  documentation treatment. "It works better" is not sufficient justification
  on its own — it must be accompanied by a data-handling review.

---

## 5. Error & Logging Rules

- Errors surfaced to the System Logs panel must be honest about what failed
  (metadata vs. transcript) and must never imply success when a step was
  skipped or degraded.
- Never log cookie contents, tokens, or PII, even at debug level.
- Retry logic must be visible to the user (a spinner/state change), not
  silent background retries that could mask repeated failures.

---

## 6. Reviewing PRs Against These Rules

Before approving any PR touching `pipeline/`, `auth/`, or `extraction/`, the
reviewer should be able to answer "yes" to all of:

- [ ] Does this avoid introducing any cookie or browser-storage access?
- [ ] Does this keep all extraction local (no new server-side calls)?
- [ ] Does this fail visibly rather than escalating silently?
- [ ] Are all new/updated dependencies pinned?
- [ ] Is `SECURITY.md` still accurate after this change?

If any answer is "no," the PR needs a design discussion before merge, not a
quick fix.

---

## 7. Git Conventions

- **Commit Messages**: Must sound human and descriptive. Do NOT use robotic prefixes or include phase numbers (like "Phase 1", "Phase 2"). Write them exactly as a developer would when explaining what broke and how it was fixed (e.g., "pin keyring dependency and remove stale test file so the suite collects cleanly").
