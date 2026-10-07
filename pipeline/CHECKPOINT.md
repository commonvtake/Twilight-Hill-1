# Old Silent Hill town + gameplay fixes 0.7.0 - 2026-10-06

User 0.6.0 test: cafe door round trip confirmed working; district loaded (logs show
model 1601056 / dzb 784320, starter sword+shield given). Reported: inventory cannot select
anything (cause: --stage test save has no items), jump not right (cause: TP autoJump HIO
mAlwaysMaxSpeedJump=1 -> forward lunge at max speed), wants combat roll and combat.

Silent Hill Core 0.7.0 (repo renamed github.com/commonvtake/Twilight-Hill-1; release
"latest-build"): jump = procAutoJumpInit then speed.y = sqrt(2*3.4*h) (h default 90 cm),
speedF/mNormalSpeed = current ground speed (0 standing). RB/GC Z (mItemTrigger BTN_Z, not
Midna-riding) = procFrontRollInit after facing mMoveAngle. Starter kit before daAlink create:
item_func_KANTERA/BOW, 2x EMPTY_BOTTLE+RED_BOTTLE, X=SLOT_1 lantern, Y=SLOT_4 bow, maxLife 25.
Stalhound daE_SH_Execute/Draw pre/post hooks present daytime 0 in SH stages (night-only AI).
SH stages: R_SP108, R_SP109, D_SB01. Startup log line reports resolved host features.

Town 0.7.0 (OldTownMods/SilentHillOldTown.dusk, id local.silent_hill.oldtown):
stage D_SB01 (Cave of Ordeals slots; only wolf-sense pat/map/chu special cases). 115 THR
tiles with SH y -6..4 in 3x3 chunks cx=(x+1)//3, cy=y//3, origin [-120cx-20,0,120cy+60] m;
chunk (0,0) = room 0 = 0.6 district (same origin/spawns/door). 18 chunks, room 10 (two 2 m
strips) skipped. Portals: floor on both sides within 1 m of the edge, |dh|<40 cm, >=1.5 m,
split <=30 m; scnChg TGSC arg1=1 arg0=exit 0..3 m inside edge (sx by width, sy 80, sz 20),
SCLS D_SB01 room/spawn, PLYR arrival 6 m inside (spawn id in angle.z low byte, ids from 2).
96 directed links. Stage dzs: RTBL N entries (num 1, room byte 0xC0|r), Env0/Enve record
x N (0x41 each, indexed by room), stage SCLS = cafe exit. Cafe room+stage SCLS retargeted
R_SP109 -> D_SB01 room 0 spawn 1. Collision per room: tris with low point <450 cm + walls +
drop barriers seeded from all arrivals. Enemies: 1 Stalhound/1250 m2, 1 Guay/2000 m2.
Validation (validate_town_stage.py): every trigger->exit->room->spawn resolves, arrivals
outside destination triggers, triggers overlap reachable floor, links symmetric, 0 open
drops, RTBL/Env decode, cafe exits. Connected from room 0: 12 rooms, 50,878 m2, 64 enemies,
largest reachable room 2.47 MB. Rooms 1,2,6,11,14 (cx -2/-3) are behind a ~10 m no-floor
gap (SH collapsed-road chasm): built but unreachable until story routes exist.
Launch-Silent-Hill.cmd -> -OldTown (DistrictTestData profile reused, Logs/OldTown).
Launch-District-Only.cmd = 0.7 single-area district + enemies (fallback).
NOT runtime tested. Next gate: Windows test of room transitions, enemies, jump/roll,
inventory; then interiors/story start (Cafe items, alley/Otherworld), school.

Rebuild: export all THR tiles to tp_work/tiles with the pinned sh_ipd2obj (export_cafe.py
builds it), tools/build_town.py, tools/package_town_stage.py, tools/validate_town_stage.py.

Previous checkpoint:

# Central district + Silent Hill Core 0.6.0 - 2026-10-06

User request: finish combining both games; pause-menu settings incl. display; Link's
combat roll/jump; continue adding the rest of Silent Hill. Full campaign NOT complete.
Inputs now in workspace: user's SH1 US disc (SLUS_007.07 sha1 f3834456, = decomp v1.1
target) and TP GZ2E01 (main.dol sha1 4997d93b) - identical to reports/inputs.json.
sh_ipd2obj recovered: belek666/sh_ipd2obj @0be5820 (linked from SH decomp docs);
export_cafe.py + build_town_source.py reproduce town/source byte-identically.

Silent Hill Core (native C++ Dusklight mod, id local.silent_hill.core 0.6.0):
source github.com/commonvtake/silent-hill-core, pinned Dusklight v2.0.3; CI builds all
platforms; main pushes publish release "latest-build" (silent_hill_core.dusk).
- Replace-hook dMw_c::collect_option_open_proc: Options on the pause (collect) screen
  shows Dusklight MenuBar (resolved dusk::ui::find_document(scope 4) +
  dusk::ui::MenuBar::show); when ui::any_document_visible() goes false sets
  mMenuProc=OPTIONS_CLOSE (rebuilds pause screen). Falls back to original page if the
  symbols do not resolve or the menu never appears (60 frames). Config can restore it.
- Pre-hook daAlink_c::checkNextAction: buffered jump press -> procAutoJumpInit(0) in
  WAIT/MOVE/ATN_*/WAIT_TURN/MOVE_TURN/SIDESTEP_LAND, human form, grounded, no event.
  Button: LB via resolved SDL_GetGamepadButton (fallback PADGetNativeButtonPressed),
  or L3/R3 via JUTGamePad::mPadStatus[0].extButton; keyboard Space via SDL keyboard.
- Pre-hook daAlink_c::create in R_SP108/R_SP109: if no sword/shield equipped, give
  Ordon Sword (COLLECT_ORDON_SWORD) + Hylian Shield, as item_func_SWORD does.
- Mods panel + "Silent Hill" menu-bar tab with options. Compiled/linked locally on
  Linux against v2.0.3 SDK; Windows build from CI. NOT runtime tested.

District 0.6.0 (DistrictMods/SilentHillDistrict.dusk, id local.silent_hill.district):
tiles THRFF00-02, THR0000-02, THR0100-02 (SH grid x -1..1, y 0..2), origin [-20,0,60] m
unchanged so spawns (500,5,0)/(160,19.84,-350) and cafe door (-60,14.84,-350) hold.
Compact BMD: C8+RGB5A3 palettes (visible texels identical to RGB5A3, cut-out mask
identical), S16 positions frac2 (max err 0.125 cm), S16 UV frac14, CLR0 INDEX8, no
normals; 35101 tris, 16 materials, 1.60 MB (0.5.0 three tiles were 1.73 MB).
Collision: triangles with lowest point < 450 cm (33736) + perimeter + 97 automatic
drop barriers (district_coverage.py) + 0.3.1 door support; 784 KB, 8191 tree nodes.
Room archive 2.39 MB (0.5.0: 2.04 MB). Archive heap on PC ~8.9 MB (m_Do_machine).
Coverage: 7379 m2 reachable from spawn on 25 cm grid, 0 open drop edges.
Everything else byte-identical to TownMods 0.5.0 (cafe, STG, room.dzr, doors, exits).
Launch-Silent-Hill.cmd -> -District (DistrictTestData, Logs/District).
Launch-Town-Previous.cmd keeps 0.5.0. Next gate: Windows playtest of district, jump,
pause settings, combat moves and door round trip; then multi-room streaming (RTBL)
for the rest of the town instead of one ever-larger room.

Rebuild: tools/export_cafe.py (exporter), tools/build_district.py, package_district.py
(needs ../build_inputs/silent_hill_core.dusk from the latest-build release).
Validate: tools/validate_district.py (writes district/coverage.png).
Python 3.13 workspace needed two local compat fixes for pinned gclib (dataclasses
_recursive_repr shim; GenericAlias-safe issubclass in bunfoe.py); output unaffected.

Previous checkpoint:

# Town expansion / PC profile 0.5.0 - 2026-10-06

User PC: Intel i5-12400F, 16 GB DDR4, RTX 3060, Windows; Xbox controller.
Target remains full Silent Hill with Twilight Princess gameplay, not complete.
Workspace cleanup removed unsaved 0.5 work; rebuilt from saved 0.4.0 + SH upload.

Three original tiles THR0000, THR0001, THR0002 placed on their original grid.
OBJ origin [-20,0,60] metres is unchanged. Road strip is approximately 120m.
9 materials, 8355 source vertices, 12298 model triangles. Collision includes
outer limits x[-150,1970], z[-5970,5970] cm, then the existing door support.
Removed old interior tile boundary by rebuilding from raw geometry.
No full town, quest scripting, SH enemies or campaign progression added.

TownMods/SilentHillTown.dusk v0.5.0 derives from FogMods0.4.0; only outdoor
model/collision and mod metadata change. Cafe, stage palettes, room.dzr,
door actors, exits and spawns remain byte-identical. 0.3.1 door fix unconfirmed.
Native runtime/render/doors/performance still require Windows user playtest.

Launch-Silent-Hill.cmd -> Launch-Cafe.ps1 -Town -PCProfile; new TownTestData,
Logs/Town, starts R_SP109,0,0,0. Fallback -LegacyGraphics uses d3d11.
Preset applied once with config backup; unrelated config keys retained.
Reapply-PC-Settings.cmd resets selected graphics keys explicitly.
PC settings: window1920x1080, VSync, Capped interpolation1 at60fps, scale0,
shadowMultiplier1, bloom0, DOF0, replacementsfalse, backendauto, FPSoverlaytrue.
Keys verified against pinned Dusklight40457c6adb381928e4b5fef6ed459ed291edd5e2.
PowerShell not executed here. No measured FPS claims.

Rebuild: export_cafe.py builds Linux exporter; build_town_source.py exports
and merges the three tiles from sh_work/assets/BG; build_town_model.py;
build_town_collision.py; package_town.py. Durable merged OBJ/MTL/TGA included.
Validate: validate_town_collision.py, validate_town.py.
Dependencies: gclib, blender_dzb_tools, numpy, Pillow, imagequant.

Previous checkpoint:

# Full-game request / fog milestone 0.4.0 — 2026-10-06

User now requests full Silent Hill 1 with fog and Twilight Princess gameplay.
Full scope is recorded in FULL-GAME-PLAN.md. This is not a completed campaign.
Current user-confirmed state: isolated cafe and street work. Door patch0.3.1
still unconfirmed. No new game areas were added in0.4.0.

Added FogMods/SilentHillFogTest.dusk, local.silent_hill.fog v0.4.0, derived from
ConnectedMods0.3.1. Only street R_SP109 model MAT3 and stage PAL*/VRB* colors/fog
changed. Native linear fog 500..1800cm, RGB153/159/156. MAT3 fog_type=2 enables
fog; FogInfo.enable is range adjustment, not fog on/off. Native dKy lighting
updates material fog from stage palettes. All source geometry and textures,
cafe bytes, door/exit and collision payloads retained exactly.

Launch-Silent-Hill.cmd invokes Launch-Cafe.ps1 -Fog, starts R_SP109,0,0,0,
uses FogTestData and Logs/Fog. Native render/door roundtrip untested. Next gates:
user visual test + roundtrip, then expand adjacent town tiles and implement
campaign progression incrementally. Do not claim full-game completion.
Rebuild fog: tools/package_fog.py. Verify: tools/validate_fog.py.
Build-time settings: fog/settings.json. No full-ROM extraction needed for this
milestone. Previous scripts and no-fog mod retained.

Previous checkpoint:

# Door-fall patch 0.3.1 — 2026-10-06

User confirms cafe and outdoor work individually; connected door in 0.3.0
causes falling into a black void. Supplied dusklight-20261006-004609.log loads
cafe model964416 / DZB72672 and KNOB20 actor. There is only one PLAY_SCENE
and one ROOM_SCENE creation; no outdoor model966848 or second scene load.
Log evidence points to failure before destination load; exact event failure
is NOT confirmed. Do not claim the root cause or runtime fix is verified.

0.3.1 retains both models, doors, spawns and reciprocal destinations. Adds
one TGSC scnChg in each room: params0xffff0100 (exit0,mode1,path255,switch255),
x/z rotations -1 disable event gates. Its local trigger range is x+/-112.5,
z[-605,-5], y[-300,900] relative to door. TGSC scale bytes[15,80,40].
Adds solid crossing floor y=-10, x+/-120, z[-650,50], side/back stops. All
original collision triangles retained; 14 added each. DZB native loader
FourCC retained, TP property words preserved. Stage-level SCLS added too,
matching room-level SCLS for native room=-1 fallback. No baseline changes.

Static validations passed: destinations/spawns/actors, raw collision tables
and tree reachability; simulated crossing samples have ground and enter
trigger behind doorway. Runtime still needs user test.
Tools: package_connected.py, door_threshold.py, validate_connected.py,
validate_thresholds.py. Dependencies: numpy, Pillow, imagequant; sibling
gclib, dzb_tools. Dusklight v2.0.3 commit40457c6adb381928e4b5fef6ed459ed291edd5e2
source grounded native scnChg params/scale, TGSC decode, stage/room exit lookup.

Previous checkpoint:

# Connected test 0.3.0 — 2026-10-06

User requested reciprocal interactive door travel. Implemented in a new
ConnectedMods/SilentHillConnected.dusk; use Launch-Connected.cmd.
Cafe is R_SP108 room0, street is R_SP109 room0. Both use explicit layer0.
Each room has one ACTR kdoor with exit index0/model0/light0 and message -1.
SCLS records (13 bytes each) target the opposite stage, room0, spawn1, layer0;
time bits 31 preserve time, wipe0. Existing launch spawn0 is retained.
Spawn1 uses normal standing mode, facing away from the local door.

Cafe: door (265,0,50), yaw -16384; return (95,5,50).
Street: door (-60,14.84375,-350), yaw 16384;
return (160,19.84375,-350). Native door model is door-knob_00.bmd already in
the stage archive. Animations/collision/events come from stock static/DoorK10.
Exterior door is a temporary wooden entrance on pavement, not a finished
Silent Hill door/facade match. No doorway mesh cutting performed.

Verified in the actual mod: actor parameters, SCLS layout, reciprocal targets,
spawn IDs/coordinates, door model parsing, no unwanted stage actors, and
unchanged validated room mesh/DZB payloads. Checked arrival 60cm footprint,
190cm headroom, and approach/animation-start floor. Both isolated collision
validators still pass. Native runtime/animation/fade/round-trip NOT tested;
next gate is user's Windows test and connected log. Do not claim runtime
success until the user confirms it.

Rebuild: tools/package_connected.py then tools/validate_connected.py.
Requires sibling gclib plus Python numpy/Pillow/imagequant. Code expects
project folder sh_tp_project. Library ZIP contains the launch folder name
SilentHill-TwilightPrincess-Test. Outdoor source/rebuild scripts remain included.

Source grounding: zeldaret/tp src/d/actor/d_a_door_knob00.cpp (parameter bits,
DoorK10 events, Open conditions and transition on animation frame15),
src/d/d_stage.cpp and include/d/d_stage.h (PLYR and SCLS),
src/d/actor/d_a_alink.cpp (normal standing arrival mode).

Previous state: user confirmed cafe 0.1.1 working. Outdoor 0.2.0 delivered but
not yet user-confirmed. Keep DZB directory FourCC; KCL causes native crash.
Separate test data folders preserve baseline/cafe/outdoor test states.
