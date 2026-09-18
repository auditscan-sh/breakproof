# Changelog

## 0.1.1

* SPDX license metadata (warning-free builds on modern setuptools).
* Tag-triggered PyPI auto-publish via Trusted Publisher — no tokens.
* CI on 3.10 / 3.11 / 3.12.

## 0.1.0

* First public cut: `scan` directories into contracts, `diff` base vs head.
* FAIL only on removed contracts, with file:line proof. Additions never fail.
* Zero dependencies, offline, read-only. Python / JS-TS / Go extractors.
* GitHub Action (`action.yml`) + library API.
