// Silent Hill Core - gameplay layer for the Silent Hill / Twilight Princess crossover.
//
// 1. Pause-screen settings: choosing "Options" on Twilight Princess's pause (collection) screen
//    opens Dusklight's own menu (Settings tab = display, graphics, audio, controls) instead of
//    the original GameCube options page. Closing that menu returns to the pause screen.
// 2. Jump button: a dedicated jump (default: left bumper / LB, keyboard Space) that uses Link's
//    native Twilight Princess jump animation and physics (procAutoJumpInit).
// 3. Starter kit: inside the Silent Hill stages Link starts with the Ordon Sword and Hylian
//    Shield (native combat moves), plus Harry's starting gear mapped to TP items: Lantern =
//    flashlight (X), Hero's Bow = handgun (Y), two Red Potions = health drinks, 5 hearts.
// 4. Dodge roll: RB (GameCube Z, unused while Midna is not riding) rolls in the stick direction,
//    or forward when the stick is idle, using Link's native front roll.
// 5. Enemies: Stalhounds (stand-ins for Silent Hill's Groaners) normally only rise at night;
//    in the Silent Hill stages their update sees midnight so they appear in the fog.
//
// All behaviour is grounded in Dusklight v2.0.3 / zeldaret tp sources:
//   src/d/d_menu_window.cpp   dMw_c::collect_option_*  (pause -> options state machine)
//   src/d/actor/d_a_alink.cpp daAlink_c::checkNextAction / procAutoJumpInit
//   src/d/d_item.cpp          item_func_SWORD / item_func_WOOD_SHIELD (equip sequence)

#include "mods/service.hpp"
#include "mods/svc/config.h"
#include "mods/svc/hook.hpp"
#include "mods/svc/log.hpp"
#include "mods/svc/ui.h"

#include "JSystem/JUtility/JUTGamePad.h"
#include "d/actor/d_a_alink.h"
#include "d/d_com_inf_game.h"
#include "d/d_item.h"
#include "d/d_item_data.h"
#include "d/d_kankyo.h"
#include "d/d_menu_window.h"
#include "d/d_save.h"
#include "dolphin/pad.h"

#include <cmath>
#include <cstdint>
#include <cstring>

DEFINE_MOD();

IMPORT_SERVICE(LogService, svc_log);
IMPORT_SERVICE(HookService, svc_hook);
IMPORT_SERVICE(ConfigService, svc_config);
IMPORT_SERVICE(UiService, svc_ui);

DEFINE_HOOK(&dMw_c::collect_option_open_proc, OptionOpenProc);
DEFINE_HOOK(&daAlink_c::checkNextAction, LinkCheckNextAction);
DEFINE_HOOK(&daAlink_c::create, LinkCreate);
DEFINE_HOOK_SYMBOL("daE_SH_Execute", int(void*), StalhoundExecute);
DEFINE_HOOK_SYMBOL("daE_SH_Draw", int(void*), StalhoundDraw);

namespace {

// ---------------------------------------------------------------- configuration

enum PauseOptionsMode : int64_t {
    PAUSE_OPTIONS_DUSKLIGHT = 0,  // Options opens Dusklight's settings menu
    PAUSE_OPTIONS_ORIGINAL = 1,   // Options opens the original GameCube options page
};

enum JumpButton : int64_t {
    JUMP_LEFT_BUMPER = 0,
    JUMP_LEFT_STICK = 1,
    JUMP_RIGHT_STICK = 2,
};

ConfigVarHandle g_cvarPauseOptions = 0;
ConfigVarHandle g_cvarJumpEnabled = 0;
ConfigVarHandle g_cvarJumpButton = 0;
ConfigVarHandle g_cvarJumpKeyboard = 0;
ConfigVarHandle g_cvarStarterGear = 0;
ConfigVarHandle g_cvarJumpHeight = 0;
ConfigVarHandle g_cvarRollEnabled = 0;
ConfigVarHandle g_cvarNightEnemies = 0;

const char* const kPauseOptions[] = {"Dusklight settings (display, audio, controls)",
                                     "Original Twilight Princess options"};
const char* const kJumpButtons[] = {"Left bumper (LB / L1)", "Left stick click (L3)",
                                    "Right stick click (R3)"};

int64_t get_int(ConfigVarHandle handle, int64_t fallback) {
    int64_t value = fallback;
    if (handle == 0 || svc_config->get_int(mod_ctx, handle, &value) != MOD_OK) {
        return fallback;
    }
    return value;
}

bool get_bool(ConfigVarHandle handle, bool fallback) {
    bool value = fallback;
    if (handle == 0 || svc_config->get_bool(mod_ctx, handle, &value) != MOD_OK) {
        return fallback;
    }
    return value;
}

ModResult register_bool(const char* name, bool def, ConfigVarHandle& out, ModError* error) {
    ConfigVarDesc desc = CONFIG_VAR_DESC_INIT;
    desc.name = name;
    desc.type = CONFIG_VAR_BOOL;
    desc.default_bool = def;
    if (svc_config->register_var(mod_ctx, &desc, &out) != MOD_OK) {
        return mods::set_error(error, MOD_ERROR, "failed to register a Silent Hill Core option");
    }
    return MOD_OK;
}

ModResult register_int(const char* name, int64_t def, ConfigVarHandle& out, ModError* error) {
    ConfigVarDesc desc = CONFIG_VAR_DESC_INIT;
    desc.name = name;
    desc.type = CONFIG_VAR_INT;
    desc.default_int = def;
    if (svc_config->register_var(mod_ctx, &desc, &out) != MOD_OK) {
        return mods::set_error(error, MOD_ERROR, "failed to register a Silent Hill Core option");
    }
    return MOD_OK;
}

// ---------------------------------------------------------------- host (Dusklight UI) access
//
// Dusklight's menu is not part of the public mod API, so the two functions needed to show it are
// resolved by name from the game's symbol manifest. Both are plain functions/member functions
// (`this` passed as the first argument), which matches the x86-64 and ARM64 calling conventions.

using FindDocumentFn = void* (*)(std::uint8_t scope);
using DocumentShowFn = void (*)(void* self);
using AnyVisibleFn = bool (*)();

constexpr std::uint8_t kDocumentScopeMenuBar = 4;  // dusk::ui::DocumentScope::MenuBar

FindDocumentFn g_findDocument = nullptr;
DocumentShowFn g_menuBarShow = nullptr;
AnyVisibleFn g_anyDocumentVisible = nullptr;

template <typename Fn>
bool resolve(const char* name, Fn& out) {
    void* addr = nullptr;
    if (svc_hook->resolve(mod_ctx, name, &addr, nullptr) != MOD_OK || addr == nullptr) {
        mods::log::warn("could not resolve {}", name);
        return false;
    }
    out = reinterpret_cast<Fn>(addr);
    return true;
}

bool host_menu_available() {
    return g_findDocument != nullptr && g_menuBarShow != nullptr && g_anyDocumentVisible != nullptr;
}

bool open_dusklight_menu() {
    if (!host_menu_available()) {
        return false;
    }
    void* menuBar = g_findDocument(kDocumentScopeMenuBar);
    if (menuBar == nullptr) {
        return false;
    }
    g_menuBarShow(menuBar);
    return true;
}

// ---------------------------------------------------------------- 1. pause-screen settings

enum class SettingsState { Idle, WaitingForMenu, MenuOpen };
SettingsState g_settingsState = SettingsState::Idle;
int g_settingsWaitFrames = 0;

void finish_settings(dMw_c* window) {
    g_settingsState = SettingsState::Idle;
    // OPTIONS_CLOSE fades out (already dark), deletes the unused options page and rebuilds the
    // pause screen exactly as backing out of the original options page does.
    window->mMenuProc = dMw_c::OPTIONS_CLOSE;
}

void on_option_open_proc(ModContext*, void* args, void* retval, void*) {
    dMw_c* window = mods::arg<dMw_c*>(args, 0);

    const bool useDusklight =
        get_int(g_cvarPauseOptions, PAUSE_OPTIONS_DUSKLIGHT) == PAUSE_OPTIONS_DUSKLIGHT &&
        host_menu_available();
    if (!useDusklight && g_settingsState == SettingsState::Idle) {
        OptionOpenProc::g_orig(window);
        return;
    }

    switch (g_settingsState) {
    case SettingsState::Idle:
        if (!open_dusklight_menu()) {
            OptionOpenProc::g_orig(window);  // fall back to the original options page
            return;
        }
        g_settingsState = SettingsState::WaitingForMenu;
        g_settingsWaitFrames = 0;
        break;
    case SettingsState::WaitingForMenu:
        if (g_anyDocumentVisible()) {
            g_settingsState = SettingsState::MenuOpen;
        } else if (++g_settingsWaitFrames > 60) {
            mods::log::warn("Dusklight menu did not appear; returning to the pause screen");
            finish_settings(window);
        }
        break;
    case SettingsState::MenuOpen:
        if (!g_anyDocumentVisible()) {
            finish_settings(window);
        }
        break;
    }
    (void)retval;
}

// ---------------------------------------------------------------- 2. jump button

// SDL is linked into Dusklight; the two calls used here are resolved at runtime so the mod still
// loads (with stick-click jumping only) if a future build hides them.
using SDLGetGamepadButtonFn = bool (*)(SDL_Gamepad* gamepad, int button);
using SDLGetKeyboardStateFn = const bool* (*)(int* numkeys);

constexpr int kSdlGamepadButtonLeftShoulder = 9;  // SDL_GAMEPAD_BUTTON_LEFT_SHOULDER (SDL3)
constexpr int kSdlScancodeSpace = 44;             // SDL_SCANCODE_SPACE

SDLGetGamepadButtonFn g_sdlGetGamepadButton = nullptr;
SDLGetKeyboardStateFn g_sdlGetKeyboardState = nullptr;

bool g_jumpHeldLastUpdate = false;
int g_jumpQueuedUpdates = 0;  // >0 while a press is waiting for the next game tick
constexpr int kJumpBufferUpdates = 8;

bool jump_button_held() {
    const int64_t button = get_int(g_cvarJumpButton, JUMP_LEFT_BUMPER);
    bool held = false;

    const u32 ext = JUTGamePad::mPadStatus[PAD_CHAN0].extButton;
    if (button == JUMP_LEFT_STICK) {
        held = (ext & PAD_BUTTON_LEFT_STICK) != 0;
    } else if (button == JUMP_RIGHT_STICK) {
        held = (ext & PAD_BUTTON_RIGHT_STICK) != 0;
    } else if (g_sdlGetGamepadButton != nullptr) {
        const s32 index = PADGetIndexForPort(PAD_CHAN0);
        SDL_Gamepad* gamepad = index >= 0 ? PADGetSDLGamepadForIndex(static_cast<u32>(index)) : nullptr;
        if (gamepad != nullptr) {
            held = g_sdlGetGamepadButton(gamepad, kSdlGamepadButtonLeftShoulder);
        }
    } else {
        // Fallback through Aurora's public pad API: reports the first native button held.
        held = PADGetNativeButtonPressed(PAD_CHAN0) == kSdlGamepadButtonLeftShoulder;
    }

    if (!held && g_sdlGetKeyboardState != nullptr && get_bool(g_cvarJumpKeyboard, true)) {
        int count = 0;
        const bool* keys = g_sdlGetKeyboardState(&count);
        held = keys != nullptr && count > kSdlScancodeSpace && keys[kSdlScancodeSpace];
    }
    return held;
}

void poll_jump_button() {
    if (!get_bool(g_cvarJumpEnabled, true)) {
        g_jumpHeldLastUpdate = false;
        g_jumpQueuedUpdates = 0;
        return;
    }
    bool menuOpen = false;
    svc_ui->is_any_document_visible(mod_ctx, &menuOpen);
    const bool held = !menuOpen && jump_button_held();
    if (held && !g_jumpHeldLastUpdate) {
        g_jumpQueuedUpdates = kJumpBufferUpdates;
    } else if (g_jumpQueuedUpdates > 0) {
        --g_jumpQueuedUpdates;
    }
    g_jumpHeldLastUpdate = held;
}

bool link_on_ground_and_free(daAlink_c* link) {
    switch (link->mProcID) {
    case daAlink_c::PROC_WAIT:
    case daAlink_c::PROC_MOVE:
    case daAlink_c::PROC_ATN_MOVE:
    case daAlink_c::PROC_ATN_ACTOR_WAIT:
    case daAlink_c::PROC_ATN_ACTOR_MOVE:
    case daAlink_c::PROC_WAIT_TURN:
    case daAlink_c::PROC_MOVE_TURN:
    case daAlink_c::PROC_SIDESTEP_LAND:
        break;
    default:
        return false;
    }
    if (link->checkWolf() || link->checkEventRun() || !link->mLinkAcch.ChkGroundHit()) {
        return false;
    }
    return true;
}

bool in_silent_hill_stage() {
    const char* stage = dComIfGp_getStartStageName();
    return stage != nullptr && (std::strcmp(stage, "R_SP108") == 0 || std::strcmp(stage, "R_SP109") == 0);
}

// Twilight Princess's auto jump is tuned for leaping off ledges: daAlinkHIO_autoJump_c0 sets
// mAlwaysMaxSpeedJump, so every jump lunges forward at full speed with a low arc. A button jump
// instead keeps Link's current ground speed (0 when standing = straight up) and uses a fixed
// take-off velocity for the chosen apex height under the auto-jump gravity (-3.4 cm/frame^2).
int do_button_jump(daAlink_c* link) {
    const f32 groundSpeed = link->checkInputOnR() ? link->speedF : 0.0f;
    const int result = link->procAutoJumpInit(0);
    if (result == 0) {
        return 0;
    }
    const f32 gravity = 3.4f;
    const f32 height = static_cast<f32>(get_int(g_cvarJumpHeight, 90));
    const f32 clamped = height < 30.0f ? 30.0f : (height > 250.0f ? 250.0f : height);
    link->speed.y = std::sqrt(2.0f * gravity * clamped);
    link->speedF = groundSpeed;
    link->mNormalSpeed = groundSpeed;
    mods::log::debug("jump: proc {} speedF {:.1f} vy {:.1f}", static_cast<int>(link->mProcID), groundSpeed, link->speed.y);
    return result;
}

// Dodge roll on RB (GameCube Z). Faces the stick direction first, so it works while standing
// still and while Z-targeting (the native A-button roll needs Link to be running).
int do_dodge_roll(daAlink_c* link) {
    if (link->checkInputOnR()) {
        link->shape_angle.y = link->mMoveAngle;
        link->current.angle.y = link->mMoveAngle;
    }
    const int result = link->procFrontRollInit();
    if (result != 0) {
        mods::log::debug("dodge roll: angle {}", static_cast<int>(link->shape_angle.y));
    }
    return result;
}

HookAction on_check_next_action(ModContext*, void* args, void* retval, void*) {
    daAlink_c* link = mods::arg<daAlink_c*>(args, 0);
    if (link == nullptr) {
        return HOOK_CONTINUE;
    }
    int result = 0;
    if (g_jumpQueuedUpdates > 0 && link_on_ground_and_free(link)) {
        g_jumpQueuedUpdates = 0;
        result = do_button_jump(link);
    } else if ((link->mItemTrigger & daAlink_c::BTN_Z) && get_bool(g_cvarRollEnabled, true) &&
               in_silent_hill_stage() && !link->checkMidnaRide() && link_on_ground_and_free(link))
    {
        result = do_dodge_roll(link);
    }
    if (result == 0) {
        return HOOK_CONTINUE;  // nothing taken (or the game refused); normal action selection
    }
    if (retval != nullptr) {
        *static_cast<int*>(retval) = result;
    }
    return HOOK_SKIP_ORIGINAL;
}

// ---------------------------------------------------------------- 3. starter kit

HookAction on_link_create(ModContext*, void*, void*, void*) {
    if (!get_bool(g_cvarStarterGear, true) || !in_silent_hill_stage()) {
        return HOOK_CONTINUE;
    }
    // Equipment and items are read while Link and the HUD load, so apply them before create runs.
    if (dComIfGs_getSelectEquipSword() == dItemNo_NONE_e) {
        dComIfGs_setCollectSword(COLLECT_ORDON_SWORD);
        dComIfGs_setSelectEquipSword(dItemNo_SWORD_e);
        dComIfGs_onItemFirstBit(dItemNo_SWORD_e);
        mods::log::info("starter kit: Ordon Sword");
    }
    if (dComIfGs_getSelectEquipShield() == dItemNo_NONE_e) {
        dComIfGs_setCollectShield(COLLECT_HYLIAN_SHIELD);
        dComIfGs_setSelectEquipShield(dItemNo_HYLIA_SHIELD_e);
        dComIfGs_onItemFirstBit(dItemNo_HYLIA_SHIELD_e);
        mods::log::info("starter kit: Hylian Shield");
    }
    if (!dComIfGs_isItemFirstBit(dItemNo_KANTERA_e)) {
        // Harry's flashlight -> Lantern (full oil), handgun -> Hero's Bow (30 arrows),
        // health drinks -> two Red Potions. Same calls the game makes when receiving them.
        item_func_KANTERA();
        dComIfGs_onItemFirstBit(dItemNo_KANTERA_e);
        item_func_BOW();
        dComIfGs_onItemFirstBit(dItemNo_BOW_e);
        for (int i = 0; i < 2; ++i) {
            item_func_EMPTY_BOTTLE();
            item_func_RED_BOTTLE();
        }
        dComIfGs_onItemFirstBit(dItemNo_EMPTY_BOTTLE_e);
        dComIfGs_setSelectItemIndex(SELECT_ITEM_X, SLOT_1);  // Lantern on X
        dComIfGs_setSelectItemIndex(SELECT_ITEM_Y, SLOT_4);  // Bow on Y
        mods::log::info("starter kit: Lantern (X), Hero's Bow (Y), 2 Red Potions");
    }
    if (dComIfGs_getMaxLife() < 25) {
        dComIfGs_setMaxLife(25);  // 5 hearts (5 units per heart)
        dComIfGs_setLife(dComIfGs_getMaxLifeGauge());
        mods::log::info("starter kit: 5 hearts");
    }
    return HOOK_CONTINUE;
}

// ---------------------------------------------------------------- 5. night-only enemies

// d_a_e_sh.cpp reads g_env_light.daytime every update and only lets Stalhounds rise between
// 19:00 and 04:59. Present midnight to their update/draw in the Silent Hill stages only, then
// restore the real time so lighting, sky and everything else are untouched.
f32 g_savedDaytime = 0.0f;
bool g_daytimeOverridden = false;

HookAction stalhound_pre(ModContext*, void*, void*, void*) {
    if (get_bool(g_cvarNightEnemies, true) && in_silent_hill_stage()) {
        g_savedDaytime = g_env_light.daytime;
        g_env_light.daytime = 0.0f;  // 00:00
        g_daytimeOverridden = true;
    }
    return HOOK_CONTINUE;
}

void stalhound_post(ModContext*, void*, void*, void*) {
    if (g_daytimeOverridden) {
        g_env_light.daytime = g_savedDaytime;
        g_daytimeOverridden = false;
    }
}

// ---------------------------------------------------------------- options window

UiWindowHandle g_optionsWindow = 0;
UiMenuTabHandle g_menuTab = 0;

void add_control(UiElementHandle pane, const UiControlDesc& desc) {
    svc_ui->pane_add_control(mod_ctx, pane, &desc, nullptr);
}

ModResult build_options_tab(
    ModContext*, UiWindowHandle, UiElementHandle left, UiElementHandle, void*, ModError*) {
    UiControlDesc c = UI_CONTROL_DESC_INIT;
    c.kind = UI_CONTROL_SELECT;
    c.label = "Pause screen Options button";
    c.help_rml = "Choose what the <b>Options</b> button on the pause screen (Start) opens.<br/>"
                 "Dusklight settings contain the display, graphics, audio and control options.";
    c.binding = UI_BINDING_CONFIG_VAR;
    c.config_var = g_cvarPauseOptions;
    c.options = kPauseOptions;
    c.option_count = 2;
    add_control(left, c);

    c = UI_CONTROL_DESC_INIT;
    c.kind = UI_CONTROL_TOGGLE;
    c.label = "Jump button";
    c.help_rml = "Adds a dedicated jump using Link's own jump animation. Works while standing, "
                 "walking, running and Z-targeting. Rolling stays on A while moving.";
    c.binding = UI_BINDING_CONFIG_VAR;
    c.config_var = g_cvarJumpEnabled;
    add_control(left, c);

    c = UI_CONTROL_DESC_INIT;
    c.kind = UI_CONTROL_SELECT;
    c.label = "Jump on controller";
    c.help_rml = "Left bumper is unused by Twilight Princess on Xbox-style controllers. "
                 "If you mapped LB to a game button, pick a stick click instead.";
    c.binding = UI_BINDING_CONFIG_VAR;
    c.config_var = g_cvarJumpButton;
    c.options = kJumpButtons;
    c.option_count = 3;
    add_control(left, c);

    c = UI_CONTROL_DESC_INIT;
    c.kind = UI_CONTROL_TOGGLE;
    c.label = "Jump on keyboard Space";
    c.binding = UI_BINDING_CONFIG_VAR;
    c.config_var = g_cvarJumpKeyboard;
    add_control(left, c);

    c = UI_CONTROL_DESC_INIT;
    c.kind = UI_CONTROL_NUMBER;
    c.label = "Jump height";
    c.help_rml = "Peak height of the jump in centimetres (Link is about 140 cm tall).";
    c.binding = UI_BINDING_CONFIG_VAR;
    c.config_var = g_cvarJumpHeight;
    c.min = 30;
    c.max = 250;
    c.step = 10;
    c.suffix = " cm";
    add_control(left, c);

    c = UI_CONTROL_DESC_INIT;
    c.kind = UI_CONTROL_TOGGLE;
    c.label = "Dodge roll on RB";
    c.help_rml = "In the Silent Hill areas, RB (GameCube Z) rolls in the direction of the stick, "
                 "even while standing still or Z-targeting.";
    c.binding = UI_BINDING_CONFIG_VAR;
    c.config_var = g_cvarRollEnabled;
    add_control(left, c);

    c = UI_CONTROL_DESC_INIT;
    c.kind = UI_CONTROL_TOGGLE;
    c.label = "Stalhounds rise in the fog";
    c.help_rml = "Stalhounds (standing in for Groaners) normally only appear at night.";
    c.binding = UI_BINDING_CONFIG_VAR;
    c.config_var = g_cvarNightEnemies;
    add_control(left, c);

    c = UI_CONTROL_DESC_INIT;
    c.kind = UI_CONTROL_TOGGLE;
    c.label = "Starter kit";
    c.help_rml = "In the Silent Hill areas, Link starts with the Ordon Sword, Hylian Shield, Lantern (X), "
                 "Hero's Bow (Y), two Red Potions and five hearts. Applies when an area loads.";
    c.binding = UI_BINDING_CONFIG_VAR;
    c.config_var = g_cvarStarterGear;
    add_control(left, c);
    return MOD_OK;
}

void on_options_closed(ModContext*, UiWindowHandle, void*) {
    g_optionsWindow = 0;
}

void open_options_window(ModContext*, void*) {
    if (g_optionsWindow != 0) {
        return;
    }
    UiTabDesc tabs[1] = {UI_TAB_DESC_INIT};
    tabs[0].title = "Silent Hill";
    tabs[0].build = build_options_tab;
    UiWindowDesc desc = UI_WINDOW_DESC_INIT;
    desc.tabs = tabs;
    desc.tab_count = 1;
    desc.on_closed = on_options_closed;
    if (svc_ui->window_push(mod_ctx, &desc, &g_optionsWindow) != MOD_OK) {
        mods::log::error("failed to open the Silent Hill options window");
    }
}

ModResult build_panel(ModContext*, UiElementHandle panel, void*, ModError*) {
    UiControlDesc c = UI_CONTROL_DESC_INIT;
    c.kind = UI_CONTROL_BUTTON;
    c.label = "Open Silent Hill options";
    c.on_pressed = open_options_window;
    add_control(panel, c);
    return MOD_OK;
}

}  // namespace

extern "C" {

MOD_EXPORT ModResult mod_initialize(ModError* error) {
    ModResult r;
    if ((r = register_int("pauseOptions", PAUSE_OPTIONS_DUSKLIGHT, g_cvarPauseOptions, error)) != MOD_OK ||
        (r = register_bool("jumpEnabled", true, g_cvarJumpEnabled, error)) != MOD_OK ||
        (r = register_int("jumpButton", JUMP_LEFT_BUMPER, g_cvarJumpButton, error)) != MOD_OK ||
        (r = register_bool("jumpKeyboard", true, g_cvarJumpKeyboard, error)) != MOD_OK ||
        (r = register_bool("starterGear", true, g_cvarStarterGear, error)) != MOD_OK ||
        (r = register_int("jumpHeight", 90, g_cvarJumpHeight, error)) != MOD_OK ||
        (r = register_bool("rollEnabled", true, g_cvarRollEnabled, error)) != MOD_OK ||
        (r = register_bool("nightEnemies", true, g_cvarNightEnemies, error)) != MOD_OK)
    {
        return r;
    }

    resolve("dusk::ui::find_document", g_findDocument);
    resolve("dusk::ui::MenuBar::show", g_menuBarShow);
    resolve("dusk::ui::any_document_visible", g_anyDocumentVisible);
    resolve("SDL_GetGamepadButton", g_sdlGetGamepadButton);
    resolve("SDL_GetKeyboardState", g_sdlGetKeyboardState);
    if (!host_menu_available()) {
        mods::log::warn("Dusklight menu functions unavailable; pause Options keeps the original page");
    }

    if ((r = mods::hook::replace<OptionOpenProc>(on_option_open_proc)) != MOD_OK) {
        return mods::set_error(error, r, "failed to hook the pause-screen Options page");
    }
    if ((r = mods::hook::add_pre<LinkCheckNextAction>(on_check_next_action)) != MOD_OK) {
        return mods::set_error(error, r, "failed to hook Link's action selection");
    }
    if ((r = mods::hook::add_pre<LinkCreate>(on_link_create)) != MOD_OK) {
        return mods::set_error(error, r, "failed to hook Link's creation");
    }

    // Optional: if a future Dusklight renames these statics, the mod still loads.
    if (mods::hook::add_pre<StalhoundExecute>(stalhound_pre) != MOD_OK ||
        mods::hook::add_post<StalhoundExecute>(stalhound_post) != MOD_OK ||
        mods::hook::add_pre<StalhoundDraw>(stalhound_pre) != MOD_OK ||
        mods::hook::add_post<StalhoundDraw>(stalhound_post) != MOD_OK)
    {
        mods::log::warn("Stalhound night hooks unavailable; they will only appear at night");
    }

    UiModsPanelDesc panel = UI_MODS_PANEL_DESC_INIT;
    panel.build = build_panel;
    svc_ui->register_mods_panel(mod_ctx, &panel);

    UiMenuTabDesc tab = UI_MENU_TAB_DESC_INIT;
    tab.label = "Silent Hill";
    tab.on_selected = open_options_window;
    svc_ui->register_menu_tab(mod_ctx, &tab, &g_menuTab);

    mods::log::info("Silent Hill Core 0.7.0 initialized (menu {}, LB {}, keyboard {})", host_menu_available() ? "ok" : "unavailable", g_sdlGetGamepadButton ? "ok" : "fallback", g_sdlGetKeyboardState ? "ok" : "unavailable");
    return MOD_OK;
}

MOD_EXPORT ModResult mod_update(ModError*) {
    poll_jump_button();
    return MOD_OK;
}

MOD_EXPORT ModResult mod_shutdown(ModError*) {
    g_settingsState = SettingsState::Idle;
    g_jumpQueuedUpdates = 0;
    return MOD_OK;
}
}
