# Optional receipt-based installation

Run from this checkout against a local Home Assistant configuration directory.
The script never connects to Home Assistant and never restarts or reloads it.

```sh
python scripts/install_urevo_local.py --config-root /path/to/ha-config
python scripts/install_urevo_local.py --config-root /path/to/ha-config --apply
```

The first command is a dry run. The destination must contain `configuration.yaml`.
An identical installation is a no-op. A different existing installation is preserved
unless `--upgrade` is specified and every previous file matches the saved receipt:

```sh
python scripts/install_urevo_local.py --config-root /path/to/ha-config --upgrade
python scripts/install_urevo_local.py --config-root /path/to/ha-config --upgrade --apply
```

Upgrades also check translations and reject unknown files or symlinks. They save the
previous component and receipt in a `.urevo-backup-*` directory under the configuration
root. A failed directory swap restores the previous component. Keep these backups and
`.urevo-local-install-receipt.json` private: they contain installation paths and hashes.
The installer does not adopt or overwrite a different HACS/manual installation.

To roll back, unload/remove the integration entry, move the current component aside,
restore `urevo_local` from the saved backup into `custom_components`, and restore
`install-receipt.json` as `.urevo-local-install-receipt.json`. Restart when convenient
and add the integration again if needed. Do not discard the current copy until the
rollback is verified. The receipt describes files only, not runtime activation.
