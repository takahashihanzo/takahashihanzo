# Customize your profile

Everything is plain SVG + Markdown. Edit, commit, then bump the `?v=` number on that file in `README.md` (GitHub caches images hard).

| What | Where |
|---|---|
| Name, roles, quote, tech pills, "About Me", footer text | `banner.svg` (search for the text; one banner works on dark + light) |
| ID-card name / handle / skills | `lanyard.svg` |
| Contact badges (email, Instagram, YouTube, LinkedIn…) | bottom of `README.md` (commented examples included) |
| Colours | matrix green `#00ff41`, `#00c853`, `#00a843`, alert red `#ff2b2b` — find & replace in all SVGs |
| Stats / languages / trophies / neofetch card / activity log / projects table | **automatic** — `scripts/update_profile.py` runs daily via `update-profile.yml` |
| Snake | `github-snake.yml` (daily) → `output` branch |

Notes
- The name in the banner/ID card is converted to vector outlines so it looks the same everywhere. To change the name, re-run an outline generator (or ask Claude to regenerate the name paths).
- Preview the card designs locally: `python3 scripts/update_profile.py --demo` (sample data) and `--empty` to reset.
- After the first push: Actions tab → run **Generate contribution snake** and **Update profile stats** once.

- `divider.svg` and `footer.svg` are static; edit the text inside them directly.
