# Security & Device Access Policy

consolesplayingconsoles connects physical hardware — retro consoles and other
devices — onto a shared network, and exposes a dashboard (Pluto) and tooling
that can reach those devices over SSH. Some of that tooling is driven by
automation and AI agents. This document states the rules that protect the
person whose hardware is on the network.

## Device access requires per-action authorization

**Connecting to a console or device is an explicit, per-command action — never a
standing grant.**

* Any connection to a physical device (e.g. `ssh wii …`) must be authorized for
  that specific command. Approving one task does **not** roll forward into
  permission to connect again later.
* Automation and AI agents must surface the **exact command** they intend to run
  on a device and obtain approval **before each connection** — including
  read-only ones.
* **Capability is not consent.** Passwordless key auth exists for convenience;
  it makes a connection *possible*, not *permitted*. The operator draws that
  line, per request.

## Least privilege & transparency

* Device access defaults to **read-only**. Anything that writes to or changes a
  device is called out explicitly and confirmed first.
* Every command run against a device is shown to the operator — no silent or
  background access.
* Scope is the minimum needed for the task at hand and nothing more.

## Credentials & secrets

* **One dedicated SSH key per host.** Never share a single key file across
  devices — generating a key for one host must never overwrite another's.
  Per-host keys are wired via `IdentityFile` + `IdentitiesOnly yes` in
  `~/.ssh/config`.
* **Private keys are never committed.** Neither are environment files with real
  data: only `*.env.sample` templates (zero real data) belong in the repo.
* Local agent memory, machine-specific config, and anything embedding an
  operator's home path stay out of version control (see `.gitignore`).

## Reporting a vulnerability

Found a way this network could expose or harm a connected device or its owner?
Please open an issue describing the problem (omit any real credentials), or
reach the project privately via the contact on
[@consolesplayingconsoles](https://instagram.com/consolesplayingconsoles).
