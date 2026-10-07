# Silent Hill with Twilight Princess gameplay

Requested target: a playable recreation of Silent Hill 1's full campaign using
Link and Twilight Princess movement, camera, combat and interaction systems.
This is a development target, not the current package's contents. It requires
area conversion and gameplay implementation; combining decomp repositories
alone does not provide a playable campaign.

## Current state

| Component | State |
|---|---|
| Cafe and one street tile | Individually confirmed working by the user |
| Reciprocal doors | 0.3.0 failed; repair 0.3.1 awaits user round-trip confirmation |
| Native outdoor fog | 0.4.0 data checks pass; Windows visual test pending |
| Three-tile street expansion | 0.5.0 packaged; static checks only, Windows test pending |
| Central district (3 x 3 tiles) | 0.6.0 packaged; static checks only, Windows test pending |
| Pause-screen settings, jump button, starter sword/shield | 0.6.0 Silent Hill Core mod; compiled for all platforms, Windows test pending |
| Old Silent Hill town (115 tiles, 17 areas) | 0.7.0 packaged; 12 areas connected, west side behind SH chasm; Windows test pending |
| Remaining interiors, other districts, Otherworld | Not implemented |
| Silent Hill story, puzzles, items and progression | Not implemented |
| Silent Hill enemies, bosses and animations | 0.7.0: Groaners/Air Screamers as native Stalhounds/Guays; no bosses or SH models |
| Campaign save/load, endings and final performance testing | Not implemented |

## Milestones and completion gates

1. **Stable playable section.** Confirm fog rendering, both door directions,
   movement and camera control. Repeated round trips must not fall, hang or
   lose collision. Establish a save/load checkpoint before expanding.
2. **Town traversal.** Convert adjoining original town tiles in bounded chunks;
   align shared edges, collision and spawn coordinates; stream/load only the
   needed areas. Test every connection and outdoor performance on the user's PC.
3. **Campaign environments.** Add the remaining districts and interiors in story
   order, including alternate-world variants. Track each converted room and exit.
4. **Progression and puzzles.** Implement explicit quest state, keys, item checks,
   puzzle interactions, locked paths and checkpoint persistence. Adapt controls
   and inventory to Twilight Princess; test fresh and resumed progress.
5. **Enemy encounters.** Convert/retarget appropriate assets and implement enemy
   behavior, damage, animations and bosses compatible with Link's combat. This
   work is separate from static room geometry conversion.
6. **Presentation.** Integrate the appropriate atmosphere, lighting, sound,
   dialogue/cutscenes and transitions without blocking progress or obscuring play.
7. **Complete campaign validation.** Play from beginning to ending, verify puzzle
   dependencies and save recovery, eliminate progression blockers, and check
   loading, memory and frame pacing on the user's PC.

Deliver a playable test at each gate. Do not label an asset preview or static
package check as runtime verification. Keep the previous working build available.
The latest package (0.7.0) contains Old Silent Hill (D_SB01, one room per 3 x 3 tile block) and the cafe.
The i5-12400F / 16 GB DDR4 / RTX 3060 profile targets a 1080p window and
60 FPS interpolated presentation. Performance has not been measured on that PC.
