# Silent Hill × Twilight Princess — progress

**Overall: ~22% of the full game built, ~5% confirmed in-game** (updated 2026-11-10, prototype 0.8.0).

| Part | Share of work | Done | Status |
|---|---|---|---|
| Tools and conversion pipeline | ~10% | ~90% | SH map tiles → Zelda models/collision, whole-town stage builder, street load zones, door builder from SH door events, validators |
| Controls, menus, settings | ~10% | ~65% | Pause-screen Options → Dusklight settings, jump (LB), dodge roll (RB), starter kit, sword/shield/items enabled in SH areas |
| Environments | ~25% | ~35% | Cafe 5to2 + all of Old Silent Hill (115 tiles, 17 street areas) + 10 building interiors behind 24 doors |
| Enemies and combat | ~15% | ~15% | Groaners → Stalhounds, Air Screamers → Guays (native Zelda AI); no bosses yet |
| Story, puzzles, items, saves | ~25% | 0% | Not started |
| Atmosphere, sound, cutscenes | ~10% | ~5% | Native fog |
| Full playthrough testing | ~5% | 0% | — |

## Confirmed on the target PC (i5-12400F / RTX 3060, Windows)
- Cafe and single street tile (0.1–0.2)
- Cafe door round trip (0.3.1 fix, confirmed with 0.6.0)
- 9-tile central district loads (0.6.0 logs)
- Whole-town stage loads and street load zones work (0.7.0 playtest)

## Fixed in 0.8.0 (from the 0.7.0 playtest)
- **Crash after walking between areas** (`Destination buffer too small`): exits were looked up in
  the stage's one-entry table while Link was between rooms. One shared exit table is now written
  to the stage and every room, and a `SafeStringCopy` guard logs instead of aborting.
- **No sword, shield or item use**: the stage inherited `ST_ROOM` from the indoor cafe template,
  which the engine treats as a no-battle area. SH stages are now `ST_FIELD`.
- **Inventory could not select or equip**: same cause (`checkCastleTownUseItem` blocks items in
  `ST_ROOM` stages).

## Built, awaiting test (0.8.0)
- 10 interiors (`THR0109`, `0205/0305`, `0207/0307`, `0309`, `0505`, `0508`, `FB07`, `FB09`,
  `FD05/FD06`, `FE08`) entered through native knob doors placed from Silent Hill's door events.
  The west side of town is reached through interiors, as in the original game.
- All doors are unlocked for now (Silent Hill story flags are not yet mapped).
- Map button is disabled in SH areas (there is no Zelda map data for them).

## Next
1. Fixes from the 0.8.0 playtest.
2. Story start: Cafe 5to2 item pickups, the opening alley and Otherworld.
3. Midwich Elementary School (first dungeon) as connected interiors.
4. Door locks and key items from the decompiled event flags; more SH enemy types, bosses.

## Repository layout
- `src/`, `CMakeLists.txt` — **Silent Hill Core**, the native Dusklight mod (built by GitHub Actions; download from the *latest-build* release).
- `pipeline/` — conversion and packaging scripts, Windows launchers, test notes and build reports.
  No game data is stored here: area mods are rebuilt from your own Silent Hill (US 1.1) and
  Twilight Princess (GZ2E01) discs. See `pipeline/CHECKPOINT.md` for the full technical log.
- `docs/assets/` — README diagrams and the generated town map (no game imagery).
