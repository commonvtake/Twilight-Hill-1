# Silent Hill × Twilight Princess — progress

**Overall: ~20% of the full game built, ~5% confirmed in-game** (updated 2026-10-06, prototype 0.7.0).

| Part | Share of work | Done | Status |
|---|---|---|---|
| Tools and conversion pipeline | ~10% | ~90% | SH map tiles → Zelda models/collision, whole-town stage builder, automatic street load zones, validators |
| Controls, menus, settings | ~10% | ~60% | Pause-screen Options → Dusklight settings, jump (LB), dodge roll (RB), starter kit |
| Environments | ~25% | ~25% | Cafe 5to2 + all of Old Silent Hill (115 tiles, 17 areas, 12 connected) |
| Enemies and combat | ~15% | ~15% | Groaners → Stalhounds, Air Screamers → Guays (native Zelda AI); no bosses yet |
| Story, puzzles, items, saves | ~25% | 0% | Not started |
| Atmosphere, sound, cutscenes | ~10% | ~5% | Native fog |
| Full playthrough testing | ~5% | 0% | — |

## Confirmed on the target PC (i5-12400F / RTX 3060, Windows)
- Cafe and single street tile (0.1–0.2)
- Cafe door round trip (0.3.1 fix, confirmed with 0.6.0)
- 9-tile central district loads (0.6.0 logs)

## Built, awaiting test (0.7.0)
- Old Silent Hill town stage (`D_SB01`, one room per 3 × 3 tile block)
- Stalhounds / Guays, jump height fix, RB dodge roll, Lantern / Bow / potions / 5 hearts

## Next
1. Fixes from the 0.7.0 playtest.
2. Story start: Cafe 5to2 item pickups, the opening alley and Otherworld.
3. Midwich Elementary School (first dungeon) as connected interiors.
4. Routes to the west side of town (beyond the chasm), more SH enemy types, bosses.

## Repository layout
- `src/`, `CMakeLists.txt` — **Silent Hill Core**, the native Dusklight mod (built by GitHub Actions; download from the *latest-build* release).
- `pipeline/` — conversion and packaging scripts, Windows launchers, test notes and build reports.
  No game data is stored here: area mods are rebuilt from your own Silent Hill (US 1.1) and
  Twilight Princess (GZ2E01) discs. See `pipeline/CHECKPOINT.md` for the full technical log.
