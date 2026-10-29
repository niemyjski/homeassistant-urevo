# Contributing

Bug reports, protocol fixtures, documentation improvements, and tests are welcome.
Keep model support explicit and separate observed hardware behavior from assumptions.
Do not include Bluetooth addresses, serial numbers, household names, IP addresses,
credentials, full diagnostics, or installation receipts. Use `00:11:22:33:44:55`
for synthetic Bluetooth addresses.

## Local checks

Use Python 3.14 in a virtual environment:

```sh
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

Protocol, transport, installer, and repository tests require only the standard
library. To check against real Home Assistant classes in the same isolated environment:

```sh
python -m pip install -r requirements-ha.txt
python scripts/check_urevo_ha.py
python -m unittest discover -s tests_ha -v
```

These checks create temporary configuration directories and mock Bluetooth. They
must never connect to live Home Assistant, a proxy, or a treadmill. GitHub Actions
runs the same checks plus Home Assistant manifest/translation validation.

## Changes

Keep parsing independent of Home Assistant. Add behavior tests for malformed data,
connection lifecycle, or control changes. Preserve disabled-by-default controls,
per-field freshness, one-action arming, safety revalidation after Request Control,
and rejection of queued/retried motor actions. Device names and addresses are not
authentication. No test may move a real belt.

Keep `strings.json` and `translations/en.json` synchronized. HACS installs the
component directory directly; this is not a PyPI package. Update the manifest
version and changelog for behavior changes. Physical acceptance requires an attended,
separately authorized session; automated tests are not hardware certification.

Submit a focused pull request describing the problem, result, checks, and limitations.
Use respectful, constructive communication. Report security defects privately as
explained in SECURITY.md. Contributions are licensed under the repository's MIT license.
