# Changelog

## Unreleased

- Update the pinned `bgutil-ytdlp-pot-provider` dependency to `1.3.1`, the
  first available maintained package line after the obsolete `0.1.0` pin.
- Add a self-contained Windows release layout with bundled Python, Node.js,
  frontend assets, and the PO Token provider built from source tag `1.3.1`.
- Pin `yt-dlp` to `2026.06.09` and configure extraction through the local
  health-checked PO Token HTTP server.
- Align the default Groq pacing preset with the free-tier
  `llama-3.3-70b-versatile` limit of 30 RPM and 12K TPM.
