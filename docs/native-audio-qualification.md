# Native-audio offline migration candidate

Status: **Offline-qualified public companion + optional installed native engine
wheel (0.2.0). No private engine prerequisite. Not deployed and not approval to
activate or retire the current backend.**

## Executed matrix

| Gate | Result |
|---|---|
| Existing integration unit suite | 230 passed |
| Companion protocol + public installed factory + policy/REST + installed wheel CLI | 32 passed (12 protocol, 10 installed-runtime, 8 policy, 2 loopback REST tests) |
| Real HA 2026.9.4 baseline runtime suite | 35 passed |
| Real HA 2026.11.1 installed-version runtime fixture | 35 passed |
| Wheel and source distribution; installed console-script help | PASS |
| Installed wheel main → genuine plugin discovery/factory → verified TLS → actual Engine → synthetic provider final → graceful shutdown | PASS |
| Real provider inference, microphone, playback or household actions | NOT RUN |
| Production install, config/pipeline changes, service restart or retirement | NOT RUN |

Hermes host: Python 3.14.9, Hermes 0.23.1, aiohttp 3.14.5. HA fixture
interpreters: Python 3.14.6. The two fixture locks remain
`requirements-test-ha-modern.txt` and `requirements-test-ha-current.txt`.
The public engine is imported from the built wheel's installed site-packages.
Actual Mnemosyne dependencies are published `mnemosyne-memory==3.15.1` and
`mnemosyne-hermes==0.7.1`, not private vendor code. No private backend, profile
plugin or auth/wire modules are on PYTHONPATH. The normal Hermes core is installed
using its supported editable public-source developer route: its build guard
explicitly refuses wheel distributions. Its declared uv dependency overrides are
needed when pip/uv resolves its editable installation (Pillow conflict otherwise).

The 2026.11 fixture uses a narrowly scoped **test-only** logger-cleanup compatibility
hook because its published pytest HA plugin trails HA. `runtime_tests/run_modern.py`
preloads HA before HTTPX plugins and resets the logger class where HA removed the
old module-level reset symbol. It does not patch production HA or the integration.

## Reproduce without production state

```
python -m unittest discover -s tests -t . -q
python -m unittest discover -s companion/tests -v
python runtime_tests/run_modern.py runtime_tests -q
uv build companion
```

Install the built wheel with `[engine]` into a clean supported Hermes runtime.
Set `HERMES_NATIVE_PACKAGED_PYTHON` to its interpreter and unset `PYTHONPATH` before
running the companion suite from outside the source package. The CLI subprocess
adds only this public repository's synthetic network fixtures to its import path.
The installed tests copy the wheel's inert shim into a disposable profile and use
the genuine PluginManager loader and factory. No private test-plugin prerequisite
exists. For each HA fixture, install the wheel/engine dependencies and supported
Hermes core without replacing that fixture's pinned HA dependency set. Both full
HA runs passed **35, with zero skips**; do not count an importorskip as qualification.

All factory tests create disposable named-profile homes with synthetic persona,
policy, PCM, and memory configuration. No production session database or shared
memory surface is opened. The real loader, `register(ctx)`, factory, Host,
PluginContext, Engine, NativeLoop, admission policy, SessionDB, MemoryManager and
Mnemosyne implementation run unchanged. Only external MCP/catalog and provider
WebSocket **network boundaries** are synthetic.

## Physical origin and history

HA obtains device, area and satellite correlation from its real registries. A
satellite must belong to the supplied device; missing or inconsistent partial
origin fails closed without text dispatch. The client sends an optional `origin`
object with exactly `device_id`, `satellite_id`, `area_id` alongside session/turn
IDs. The bridge intersects it with the credential's explicitly selected finite
binding set and verifies the authoritative engine-policy area. The Engine still
receives its existing four-field IDs; the transport does not rewrite its policy.

A credential defaults to one device/satellite pair. `--bindings-file` can select
an explicit nonempty list of at most 64 policy-authorized pairs, including the
primary pair. No wildcard or automatic full-household grant exists. Missing origin
is allowed only for the backward-compatible single-principal endpoint. Multi-device
endpoints require it. The bearer authenticates **HA as the caller**, not satellite
hardware independently; keep it private and scoped to the intended HA entry.

Actual HA → TLS client → companion → genuine factory/Engine tests assert:

* Registry device/satellite/area reaches persisted Engine origin metadata.
* Same-device follow-up preserves conversation identity and semantic history.
* A second device using the same HA conversation ID creates a separate native
  session and receives none of the first device's semantic history.
* Forged area and mismatched registry satellite/device are rejected before Engine
  inference; no native error is retried through the ordinary text endpoint.
* Activity finishes and entry unload leaves no transport heartbeat tasks.

The delayed-capture test now waits **15.05 real seconds** before delivering PCM.
HA owns VAD/listening; the adapter retains its 60-second safety ceiling and
independent 1 MiB byte budget. The ordinary text/session/silence/naming tests remain
unchanged and pass. This is not a physical listening test.

## Session and memory ownership: no invented one-DB requirement

The current normal Hermes session contract uses `hermes_state.SessionDB` (the
process registry's `acquire()` constructs that class). Selecting
`memory.provider: mnemosyne` loads a **memory provider**, not a replacement session
DB. Installed-source inspection did not find a `MnemosyneSessionDB` backend.
The authentic native factory uses the same class and profile-local `state.db`.
Real Mnemosyne memory uses its separate profile-owned store. This separation is
not evidence of a configuration bypass and is **not a migration blocker**.

The regression test opens the normal registry in an isolated owning profile,
compares the actual class/path with the factory, loads the actual configured memory
provider, then runs a native turn while an unrelated profile is the outer context.
It verifies restored outer context, no unrelated-profile database, and unchanged
isolated default-root database. The earlier `ACTUAL_ONE_DB False` observation was
accurate; interpreting it as a requirement to consolidate databases was not.
Do not migrate, relabel, or replace either production store to satisfy that claim.

Authoritative architecture references:
[Hermes memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory),
[memory providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers),
[profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles).
Installed source and executed profile tests establish the specific runtime contract.

## Security and uncertain effects

* Constant-time bearer comparison, TLS required, redirects refused, profile and
  capability types exact. Both untrusted and **expired but trusted** certificates
  fail without PCM dispatch. Certificate renewal and opaque-bearer rotation remain
  owner-managed; the bearer is not a signed expiring lease.
* Admission is atomically reserved before PCM in the existing Engine database.
  A separate-interpreter replay attempt is rejected, as are fresh-connection and
  changed-session replays. Standalone instances must share the old owner's
  exclusive lifecycle lock; a new lock is not an acceptable migration workaround.
* Reservation storage is bounded at 100,000 identities and fails closed. Tests fill
  the bound and verify no eviction/reacceptance. There is **no automatic pruning**:
  deleting old identities while credentials remain valid would re-enable replay.
  Maintenance requires a drained owner, revoked old credential, backup and explicit
  approval; this candidate never silently cleans the journal.
* Capture handles are one-use, expire in 30 seconds, and are limited to four entries.
  Expired handles are purged on use/insertion; entry unload clears memory.
* Actual Engine cancellation after a synthetic service-dispatch network handoff
  keeps the uncancellable effect worker pending, refuses another turn, records
  uncertain interruption and refuses replay. It never emits a successful final
  for that cancelled turn. The transport never retries via another writer.
* Catalog mismatch is refused before provider PCM. Missing final acknowledgement
  cancels and records interruption, not a final semantic response.
* Bounded upload/message/deadline limits remain. Public errors are fixed strings;
  provider errors, credentials and profile paths never cross the wire. Capture
  marker text is rejected in final output before downstream speech or text use.

Negative TLS tests intentionally produce loopback handshake-reset diagnostics.
Installed-runtime tests also expose dependency ResourceWarnings for retained
SQLite/Beam handles; these are not hidden or represented as production leak tests.

## Public compatibility and exact remaining gates

The minimal extraction is implemented in the optional wheel engine package:
genuine owner-parameterized Host, existing Sessions/NativeLoop/Engine, reusable
finite Policy/Capabilities, PCM conversion and MIT-licensed provider wire/signing
subset. Its profile-install shim exports `register(ctx)`/`create_engine` and
declares provider auth for the real SDK caller check. No private imports, persona,
credentials, binding IDs or auth paths ship. Switch review and select enums are
explicit runtime configuration; no household enum/default-grant table is copied.
See [the grounded extraction plan](native-engine-extraction.md) and
[package provenance](../companion/hermes_native_engine/PROVENANCE.md).

Read-only private qualification supplied the unchanged existing production policy
to the **same installed public factory** under a synthetic isolated profile.
Every SQLite connection was guarded to that disposable home. No production DB was
opened; no sessions, provider requests or tool dispatch occurred. Real schema
construction preserved 16 native versus 15 text capabilities, with `finish_turn`
as the sole difference. Those are observed conditions, not a hard-coded limit.
Production profile/config/policy/facade hashes were unchanged. Only private
candidate factory options were written, not applied.

A real compatibility pitfall was reproduced: the numerically newer PyPI adapter
`mnemosyne-hermes==3.1.0` does not preserve owning-home storage over repeated
isolated profiles. The supported maintained adapter is 0.7.1. The public factory
now rejects unqualified memory versions **before database construction**, with a
RED/GREEN regression. Wildcard physical bindings are also explicitly refused.
Completed-item acknowledgement, finish_turn metadata, cancellation/uncertain
effects, replay, origin/history isolation and real profile memory remain tested.

Hermes still has no core native-engine registry; the loaded-module/profile-scope
compatibility seam is version-qualified, not a new framework or SDK claim.
The retained partial security review is **not a clean security stamp**.

Remaining live gates require new explicit approval: trusted production TLS/managed
credential provisioning if absent, owner-controlled listener replacement (one
same-owner service cycle plus one HA restart), same-entry options and the
existing native pipeline's capture/conversation routing, real provider negotiation,
physical capture/follow-up/Piper playback, and authorized household-tool parity.
Production capability policy must be reused, not narrowed to the synthetic test
catalog or widened to defaults. The existing text entry and memory/session owners
must remain intact. Any unrelated original ValueError requires reproduction before
changing it.

## Retirement is after acceptance only

The live service owner was rechecked read-only: native listener → recovery
supervisor → `s6-supervise native-audio`. Private PID/uid/path/hash, HA versions,
entry/pipeline and activation/rollback receipts stay outside the public fork.
No listener, integration, profile or pipeline was changed.

After explicit approval, back up exact current integration bytes, entry options,
pipelines and service configuration; provision the candidate under the same owner
and existing lifecycle lock; retain the existing conversation entry and native
pipeline identity/Piper configuration; switch via supported HA APIs. Keep the old
integration and listener material for rollback. Only after live acceptance retire
the old capture integration and listener through their actual owners. Never remove
shared policy, tools, persona or session/memory databases. No upstream PR is implied.
