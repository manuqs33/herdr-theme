#!/usr/bin/env python3
"""Sync Herdr with Omarchy's active color palette."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

THEME = Path(os.environ.get("OMARCHY_THEME_PATH", Path.home() / ".local/state/omarchy/current/theme/colors.toml"))
CONFIG = Path(os.environ.get("HERDR_CONFIG_PATH", Path.home() / ".config/herdr/config.toml"))

ANSI_ALIASES = {
    "selection": "selection_background",
    "muted": "color8",
    "red": "color1",
    "green": "color2",
    "yellow": "color3",
    "blue": "color4",
    "magenta": "color5",
    "cyan": "color6",
}
REQUIRED_COLORS = {"background", "foreground", "red", "green", "yellow", "blue"}


def rgb(color: str) -> tuple[int, int, int]:
    value = color.removeprefix("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(color: str) -> float:
    channels = [value / 255 for value in rgb(color)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def blend(background: str, foreground: str, opacity: float) -> str:
    channels = [round(bg * (1 - opacity) + fg * opacity) for bg, fg in zip(rgb(background), rgb(foreground))]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def first_readable(colors: dict[str, str], background: str, *names: str) -> str:
    candidates = [colors[name] for name in names if name in colors]
    return next((color for color in candidates if contrast(color, background) >= 4.5), max(candidates, key=lambda color: contrast(color, background)))


def semantic_colors(colors: dict[str, str]) -> dict[str, str]:
    normalized = colors.copy()
    for name, ansi_name in ANSI_ALIASES.items():
        if name not in normalized and ansi_name in colors:
            normalized[name] = colors[ansi_name]

    missing = REQUIRED_COLORS - normalized.keys()
    if missing:
        raise ValueError(f"theme is missing required colors: {', '.join(sorted(missing))}")
    return normalized


def custom_theme(colors: dict[str, str]) -> dict[str, str]:
    colors = semantic_colors(colors)
    background = colors["background"]
    foreground = colors["foreground"]
    selection = colors.get("selection", colors.get("lighter_background", background))
    if contrast(foreground, selection) < 4.5:
        subtle_selection = blend(background, foreground, 0.18)
        selection = subtle_selection if contrast(foreground, subtle_selection) >= 4.5 else background
    accent = first_readable(colors, background, "accent", "blue", "magenta", "cyan", "green", "red", "orange", "foreground")
    secondary = first_readable(colors, background, "muted", "light_foreground", "dark_foreground", "bright_foreground", "foreground")

    return {
        "accent": accent,
        "panel_bg": background,
        "surface0": "reset",
        "surface1": selection,
        "surface_dim": selection,
        "overlay0": secondary,
        "overlay1": foreground,
        "text": foreground,
        "subtext0": secondary,
        "mauve": colors.get("magenta", accent),
        "green": colors["green"],
        "yellow": colors["yellow"],
        "red": colors["red"],
        "blue": colors["blue"],
        "teal": colors.get("cyan", colors["blue"]),
        "peach": colors.get("orange", colors["yellow"]),
    }


def render(config: str, theme: dict[str, str]) -> str:
    block = "[theme.custom]\n" + "\n".join(f'{key} = "{value}"' for key, value in theme.items()) + "\n\n"
    pattern = re.compile(r"(?ms)^\[theme\.custom\]\n.*?(?=^\[|\Z)")
    if pattern.search(config):
        config = pattern.sub(block, config, count=1)
    else:
        config = config.rstrip() + "\n\n" + block

    foreground = theme["subtext0"]
    block = (
        "[ui.sidebar.agents]\n"
        "row_gap = 0\n"
        "rows = [\n"
        f'  ["state_icon", "workspace", {{ token = "tab", fg = "{foreground}", bold = false, dim = false }}],\n'
        f'  [{{ token = "agent", fg = "{foreground}", bold = false, dim = false }}],\n'
        "]\n\n"
    )
    pattern = re.compile(r"(?ms)^\[ui\.sidebar\.agents\]\n.*?(?=^\[|\Z)")
    match = pattern.search(config)
    if not match:
        return config.rstrip() + "\n\n" + block

    section = re.sub(
        r'(\{ token = "(?:tab|agent)", fg = ")[^"]+',
        rf"\g<1>{foreground}",
        match.group(),
    )
    return config[: match.start()] + section + config[match.end() :]


def apply(theme_path: Path = THEME, config_path: Path = CONFIG, reload_server: bool = True) -> None:
    colors = tomllib.loads(theme_path.read_text())
    config_path = config_path.resolve()  # a dotfiles manager may symlink this file
    config_path.parent.mkdir(parents=True, exist_ok=True)
    current = config_path.read_text() if config_path.exists() else '[theme]\nname = "terminal"\n'
    updated = render(current, custom_theme(colors))

    with tempfile.NamedTemporaryFile("w", dir=config_path.parent, delete=False) as candidate:
        candidate.write(updated)
        candidate_path = Path(candidate.name)

    env = os.environ | {"HERDR_CONFIG_PATH": str(candidate_path)}
    check = subprocess.run(["herdr", "config", "check"], env=env, capture_output=True, text=True)
    if check.returncode:
        candidate_path.unlink()
        raise SystemExit(check.stderr or check.stdout)

    candidate_path.replace(config_path)
    if reload_server and os.environ.get("HERDR_THEME_NO_RELOAD") != "1":
        subprocess.run(["herdr", "server", "reload-config"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def self_test() -> None:
    colors = tomllib.loads(THEME.read_text())
    theme = custom_theme(colors)
    assert contrast(theme["accent"], theme["panel_bg"]) >= 4.5
    assert contrast(theme["subtext0"], theme["panel_bg"]) >= 4.5
    rendered = render("[theme]\nname = \"terminal\"\n", theme)
    assert rendered.count("[theme.custom]") == 1
    assert rendered.count("[ui.sidebar.agents]") == 1
    assert rendered.count(f'fg = "{theme["subtext0"]}"') == 2
    assert rendered.count("bold = false") == 2
    assert rendered.count("dim = false") == 2
    custom_rows = '[ui.sidebar.agents]\nrows = [[{ token = "agent", fg = "#000000" }, "terminal_title"]]\n'
    rendered = render(custom_rows, theme)
    assert 'fg = "' + theme["subtext0"] + '"' in rendered
    assert '"terminal_title"' in rendered

    ansi = {
        "foreground": "#ffffff",
        "background": "#122738",
        "selection_background": "#0050a4",
        **{f"color{i}": color for i, color in enumerate([
            "#000000", "#ff628c", "#3ad900", "#ffc600",
            "#0088ff", "#fb94ff", "#80fcff", "#ffffff",
            "#0050a4", "#ff628c", "#3ad900", "#ffc600",
            "#0088ff", "#fb94ff", "#80fcff", "#ffffff",
        ])},
    }
    ansi_theme = custom_theme(ansi)
    assert ansi_theme["red"] == ansi["color1"]
    assert ansi_theme["green"] == ansi["color2"]
    assert ansi_theme["yellow"] == ansi["color3"]
    assert ansi_theme["blue"] == ansi["color4"]
    assert ansi_theme["mauve"] == ansi["color5"]
    assert ansi_theme["teal"] == ansi["color6"]

    ansi["red"] = "#abcdef"
    assert custom_theme(ansi)["red"] == ansi["red"]

    ansi["selection_background"] = ansi["foreground"]
    ansi_theme = custom_theme(ansi)
    assert contrast(ansi_theme["text"], ansi_theme["surface_dim"]) >= 4.5

    try:
        custom_theme({key: value for key, value in ansi.items() if key != "foreground"})
    except ValueError as error:
        assert str(error) == "theme is missing required colors: foreground"
    else:
        raise AssertionError("missing foreground was accepted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("theme_name", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    self_test() if args.self_test else apply()
