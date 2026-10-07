# Silent Hill Core

Gameplay layer for the Silent Hill / Twilight Princess crossover, built for **Dusklight v2.0.3**.

## Features

| Feature | How to use |
|---|---|
| **Settings from the pause screen** | Press **Start**, pick **Options**. Dusklight's menu opens: the **Settings** tab has display (fullscreen, VSync, resolution scale, frame rate, interpolation), graphics, audio and controls. Close it (B / Esc) to return to the pause screen. |
| **Jump button** | **Left bumper (LB)** on an Xbox controller, or **Space** on keyboard. Uses Link's own jump animation with a fixed height (default 90 cm, adjustable); standing jumps go straight up, running jumps keep Link's speed. |
| **Dodge roll** | **RB** rolls in the stick direction (forward if the stick is idle), even standing still or while Z-targeting. A while running still does the normal roll. |
| **Combat moves** | Sword (X), **side hop / backflip** (hold lock-on, A + left/right/back), **jump attack** (lock onto an enemy, A), shield (hold right trigger). |
| **Starter kit** | In the Silent Hill areas Link carries the Ordon Sword, Hylian Shield, **Lantern** (flashlight, GameCube X = Xbox **B**), **Hero's Bow** (handgun, Y, 30 arrows), two **Red Potions** (health drinks) and five hearts. |
| **Enemies** | Stalhounds (Groaners) rise from the ground in the fog; they normally only appear at night. |

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
