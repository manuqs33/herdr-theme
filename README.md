# Herdr Theme Sync

[Herdr](https://herdr.dev) does not apply its `terminal` theme correctly with every terminal-inherited color palette. This can produce low-contrast text and overly strong selected surfaces.

This plugin syncs the active Omarchy theme tokens with Herdr's configuration. It keeps Herdr readable when the Omarchy theme changes and reloads the configuration without restarting Herdr's panes.

## Requirements

- Omarchy 4 with the Quattro shell
- Herdr
- Python 3.11 or newer

## Install

```sh
omarchy plugin add https://github.com/andy-spike/herdr-theme.git --enable
```

The service applies the current palette when it starts and after every Omarchy theme change.

## Remove

```sh
omarchy plugin remove io.github.andy-spike.herdr-theme-sync
```

Removal stops automatic syncing. It leaves the last valid Herdr palette in `~/.config/herdr/config.toml`.

## Development

```sh
omarchy plugin validate .
python3 sync-herdr-theme.py --self-test
```

The plugin only reads Omarchy's active `colors.toml`. It writes Herdr's user config and calls `herdr server reload-config`.
