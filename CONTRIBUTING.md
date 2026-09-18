# Contributing

Bug reports and framework requests welcome. PRs welcome more.

## Issues

* **Bug:** what you ran, what you expected, what happened. Paste the
  `breakproof scan` endpoint count — "it found nothing" is usually the
  extractor not knowing your framework, which is a framework request.
* **Framework request:** framework name + one real route snippet. That's
  the whole spec. v0.2 is literally built from these.

## PRs

* Keep it stdlib-only. No new dependencies, ever.
* Keep it read-only. No deletes, no writes except explicit `--out` paths.
* Add a test. `pytest` must stay green on 3.10–3.12.
* Small beats clever. One pattern per PR.

## Security

Don't open public issues for vulnerabilities — see `SECURITY.md`.
