# Silent Hill Core

Gameplay layer for the Silent Hill / Twilight Princess crossover, built for **Dusklight v2.0.3**.

## Features

| Feature | How to use |
|---|---|
| **Settings from the pause screen** | Press **Start**, pick **Options**. Dusklight's menu opens: the **Settings** tab has display (fullscreen, VSync, resolution scale, frame rate, interpolation), graphics, audio and controls. Close it (B / Esc) to return to the pause screen. |
| **Jump button** | **Left bumper (LB)** on an Xbox controller, or **Space** on keyboard. Uses Link's own jump animation. Works standing, walking, running and while Z-targeting. |
| **Combat moves** | Link starts with the Ordon Sword and Hylian Shield in the Silent Hill areas, so the native moves work: **roll** (A while running), **side hop / backflip** (hold Z-target, A + left/right/back), **jump attack** (Z-target an enemy, A). |

The **Silent Hill** tab in the Dusklight menu (View/Back button or F1) lets you switch the jump to
a stick click, turn off keyboard Space, restore the original Twilight Princess options page, or
disable the starter gear.

## Install

1. Download the build: **Actions** tab → newest green run → artifact **mod-combined** (or **mod-windows-amd64**).
2. Unzip it and copy `silent_hill_core.dusk` into the `mods` folder of your Silent Hill test package
   (next to `SilentHillTown.dusk`), or `%APPDATA%\TwilitRealm\Dusklight\mods` for normal play.

## Build locally

```sh
cmake -B build
cmake --build build
```

GitHub Actions builds Windows, Linux, macOS and Android on every push.
