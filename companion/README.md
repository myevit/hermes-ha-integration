# Optional native-audio companion (experimental)

A real HTTPS/WSS protocol peer for the existing `hermes_conversation` entry. It
wraps an **already installed, explicitly selected, profile-owned native engine**;
it is not another agent, transcription fallback, provider implementation, or HA
integration domain. Ordinary text still uses the unchanged upstream API.

## Dependency / SDK checkpoint — read before installing

Hermes 0.23.1's documented `PluginContext` supports tools and CLI commands, but
neither the installed source nor the official plugin interface declares a native
conversation-engine registry/factory SDK. Hermes Talk's separately installed
transport is not such a core SDK. Therefore **this package does not provide
out-of-box native inference**. An independently installed plugin must implement
the following interface; no private plugin or policy is included here:

* `register(ctx)` receives a genuine Hermes `PluginContext` through its loader.
* Public `create_engine(**explicit_options)` returns the actual callable native
  engine. No synthetic host/context, all-tools grant or default-profile fallback.
* `await engine(pcm16_mono_16k, ids)` returns final text only after authoritative
  provider acknowledgement and policy-bounded tool/memory execution.
* `engine.take_followup(ids)` consumes the corresponding final boolean.
* `engine.host.ctx`, `engine.host.home`, `engine.host.scope_home()`,
  `engine.db.db_path`, and `engine.policy.binding(ids)` identify and validate the
  actual owner, profile-local database and finite device binding.
* Cancellation must cancel the provider response and persist interrupted status,
  not a successful final. Uncancellable effect workers must continue to exclude
  conflicting/new inference until their outcome is known (`engine.pending` in
  the qualified dependency). No retry or alternate text writer is permitted.

`load_engine()` is a small, explicitly version-qualified 0.23.1 compatibility
seam using the loaded plugin's `create_engine`. It uses Hermes' plugin manager
and its internal loaded-module map, **not a claimed public native-engine SDK**.
A future supported core SDK can replace that seam without changing the peer.
The optional installed-factory qualification tests exercise a real separately
installed implementation and real memory; ordinary protocol tests explicitly
label their synthetic inference boundary.

## Standalone lifecycle

Install this directory in the **owning Hermes runtime environment**, not inside
HA. The engine dependency and its provider transport dependencies must already
be installed and qualified there. No install/restart is performed by this repo.

```
python -m pip install ./companion
hermes-ha-native-companion --help
```

All of these are explicit CLI options: `--home` (a named `profiles/<profile>`
home), `--profile`, `--engine-plugin`, `--factory-options` (owner-only JSON kwargs
for that plugin's factory), `--device-id`, `--satellite-id`, `--credential-file`
(managed high-entropy bearer credential, mode 0600), `--tls-cert`, `--tls-key`,
`--exclusive-lock` (the **existing backend's** lifecycle lock), optional `--bind`
(default loopback) and `--port` (default 8444). No automatic credential generation,
HA secret writes, profile edits, daemon installation or administrative tooling.
TLS is mandatory; configure a certificate trusted by HA. No `ssl=False` mode.
The factory options and credential must be owned by the running uid and have no
group/other permissions. Provider secrets stay with the dependency plugin.

The CLI runs only the selected profile's enabled plugins and never enables all
tools. The configured factory remains responsible for a finite tool catalog and
admission policy. Do not install an unreviewed factory into a privileged profile.

One credential is intentionally bound to one explicit device/satellite principal
in this version-one wire contract, because the HA adapter currently sends no
physical device identity. **Do not share this endpoint/credential across physical
devices.** Multi-device routing and physical-origin authentication remain a
migration gate; this restriction is real, not presented as complete household
policy parity. The engine's full policy is reused, never republished or replaced.

## Wire and failure semantics

* `GET /v1/native/capabilities`: exact existing client version/profile/PCM limits,
  replay protection, cancellation and final-only flags. Bearer auth before work.
* `WSS /v1/native`: `start` JSON, binary PCM chunks (at most 32000 bytes), `end`
  JSON, then the exact correlated `final` schema consumed by HA's `native.py`.
* PCM is memory-only, at most 1 MiB, never stored by the transport. HA owns VAD
  and capture timing (60-second capture ceiling; byte budget is independent).
* An atomic SQLite reservation in the **existing engine database file** is made
  before accepting audio. It contains only profile/device/satellite/turn identity,
  no PCM/transcript/session rows. Replays fail even if session changes or service
  restarts. Reservations are never evicted automatically; capacity fails closed.
  Existing Engine SessionDB remains the only conversation writer. This journal
  is NOT a claim that installed Hermes and memory already share one database.
* One active exchange per process; the engine remains the authoritative policy
  and cross-process admission owner. The shared lifecycle lock is mandatory for
  standalone execution. Never run parallel listener implementations for one owner.
* Disconnect, extra frames, explicit cancel, upload overflow, bad provider result
  or timeout cancels the worker; reservation remains burned. No late successful
  final or fallback inference is emitted. Client and server have bounded 55-second
  exchange deadlines, not periodic heartbeat timers that can outlive HA unload.
* Generic errors only. Raw provider exceptions, credentials and private paths are
  not returned. Production CLI disables HTTP access logs.

## Qualification

```
python -m unittest discover -s companion/tests -v
```

The 10 protocol tests use real verified loopback TLS and the actual HA client
source. Four additional tests require `HERMES_NATIVE_TEST_PLUGIN` (a separately
installed native plugin directory), `HERMES_NATIVE_TEST_PROFILE` (its genuine
profile name) and the dependency's runtime on `PYTHONPATH`. They use the real
installed loader, factory, Engine, Host, PluginContext, SessionDB, MemoryManager
and Mnemosyne provider in a disposable named profile home. Only provider and MCP
**network** boundaries are synthetic; production home/config/policy is not used.
They verify two-turn history, memory identity/isolation, wrong profile, catalog
acknowledgement before PCM, and cancellation during missing final acknowledgement.

See [qualification](../docs/native-audio-qualification.md) for executed versions,
HA 2026.11 fixture compatibility, storage mismatch and all remaining gates.
No real provider/cloud, microphone, playback or physical device test is implied.
