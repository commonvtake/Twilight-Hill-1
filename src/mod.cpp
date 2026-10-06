// Silent Hill Core - gameplay layer for the Silent Hill / Twilight Princess crossover.
//
// 1. Pause-screen settings: choosing "Options" on Twilight Princess's pause (collection) screen
//    opens Dusklight's own menu (Settings tab = display, graphics, audio, controls) instead of
//    the original GameCube options page. Closing that menu returns to the pause screen.
// 2. Jump button: a dedicated jump (default: left bumper / LB, keyboard Space) that uses Link's
//    native Twilight Princess jump animation and physics (procAutoJumpInit).
// 3. Starter gear: inside the Silent Hill stages Link starts with the Ordon Sword and Hylian
//    Shield so the native combat moves (roll, side hop, backflip, jump attack) are available.
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
#include "d/d_item_data.h"
#include "d/d_menu_window.h"
#include "d/d_save.h"
#include "dolphin/pad.h"

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

bool link_can_jump(daAlink_c* link) {
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

HookAction on_check_next_action(ModContext*, void* args, void* retval, void*) {
    if (g_jumpQueuedUpdates <= 0) {
        return HOOK_CONTINUE;
    }
    daAlink_c* link = mods::arg<daAlink_c*>(args, 0);
    if (link == nullptr || !link_can_jump(link)) {
        return HOOK_CONTINUE;
    }
    g_jumpQueuedUpdates = 0;
    const int result = link->procAutoJumpInit(0);
    if (result == 0) {
        return HOOK_CONTINUE;  // the game refused the jump; run normal action selection
    }
    if (retval != nullptr) {
        *static_cast<int*>(retval) = result;
    }
    return HOOK_SKIP_ORIGINAL;
}

// ---------------------------------------------------------------- 3. starter gear

bool in_silent_hill_stage() {
    const char* stage = dComIfGp_getStartStageName();
    return stage != nullptr && (std::strcmp(stage, "R_SP108") == 0 || std::strcmp(stage, "R_SP109") == 0);
}

HookAction on_link_create(ModContext*, void*, void*, void*) {
    if (!get_bool(g_cvarStarterGear, true) || !in_silent_hill_stage()) {
        return HOOK_CONTINUE;
    }
    // Equipment is read while Link's models load, so apply it before the original create runs.
    if (dComIfGs_getSelectEquipSword() == dItemNo_NONE_e) {
        dComIfGs_setCollectSword(COLLECT_ORDON_SWORD);
        dComIfGs_setSelectEquipSword(dItemNo_SWORD_e);
        dComIfGs_onItemFirstBit(dItemNo_SWORD_e);
        mods::log::info("starter gear: Ordon Sword equipped");
    }
    if (dComIfGs_getSelectEquipShield() == dItemNo_NONE_e) {
        dComIfGs_setCollectShield(COLLECT_HYLIAN_SHIELD);
        dComIfGs_setSelectEquipShield(dItemNo_HYLIA_SHIELD_e);
        dComIfGs_onItemFirstBit(dItemNo_HYLIA_SHIELD_e);
        mods::log::info("starter gear: Hylian Shield equipped");
    }
    return HOOK_CONTINUE;
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
    c.kind = UI_CONTROL_TOGGLE;
    c.label = "Starter sword and shield";
    c.help_rml = "In the Silent Hill areas, Link starts with the Ordon Sword and Hylian Shield "
                 "so side hops, backflips and jump attacks work. Applies when an area loads.";
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
        (r = register_bool("starterGear", true, g_cvarStarterGear, error)) != MOD_OK)
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

    UiModsPanelDesc panel = UI_MODS_PANEL_DESC_INIT;
    panel.build = build_panel;
    svc_ui->register_mods_panel(mod_ctx, &panel);

    UiMenuTabDesc tab = UI_MENU_TAB_DESC_INIT;
    tab.label = "Silent Hill";
    tab.on_selected = open_options_window;
    svc_ui->register_menu_tab(mod_ctx, &tab, &g_menuTab);

    mods::log::info("Silent Hill Core initialized");
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
