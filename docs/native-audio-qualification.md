# Native-audio offline migration candidate

Status: **Offline-qualified optional adapter with a separately installed real
engine. Not deployed, not an out-of-box public inference engine, and not approval
to retire the current backend.**

## Executed matrix

| Gate | Result |
|---|---|
| Existing integration unit suite | 230 passed |
| Companion protocol + authentic installed factory + installed wheel CLI | 20 passed (12 protocol, 8 installed-runtime tests) |
| Real HA 2026.9.4 baseline runtime suite | 35 passed |
| Real HA 2026.11.1 installed-version runtime fixture | 35 passed |
| Wheel and source distribution; installed console-script help | PASS |
| Installed wheel main → genuine plugin discovery/factory → verified TLS → actual Engine → synthetic provider final → graceful shutdown | PASS |
| Real provider inference, microphone, playback or household actions | NOT RUN |
| Production install, config/pipeline changes, service restart or retirement | NOT RUN |

Hermes host: Python 3.14.9, Hermes 0.23.1, aiohttp 3.14.5. HA fixture
interpreters: Python 3.14.6. The two fixture locks remain
`requirements-test-ha-modern.txt` and `requirements-test-ha-current.txt`.
The actual installed engine and its real Mnemosyne memory implementation are
loaded from the explicitly supplied runtime, not shipped in this repository.

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

Installed tests require `HERMES_NATIVE_TEST_PLUGIN` and
`HERMES_NATIVE_TEST_PROFILE`, plus the genuine engine's runtime dependencies on
`PYTHONPATH`. HA tests append `HERMES_NATIVE_TEST_PATHS` only after HA has loaded,
so Hermes' dependencies do not replace the selected HA fixture. The packaged CLI
test additionally requires `HERMES_NATIVE_PACKAGED_PYTHON`: a disposable interpreter
with the built wheel installed, not a source-directory import. Without these
explicit inputs the dependency-specific tests **skip**, not pass.

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

The package implements transport, not generic inference. Hermes 0.23.1 has no
supported native-engine factory registry; the version-qualified loader uses the
manager's internal loaded-plugin map. The installed implementation is private and
profile-specific. **A public user cannot obtain native inference merely by
installing this wheel.**

Minimal later ship-compatible extraction: an independently installable plugin
exposing `register(ctx)`/`create_engine`, a parameterized owner/context/session
adapter, the existing finite policy interface and provider NativeLoop, and its
small PCM resampling/auth/wire dependencies. Remove literal profile constraints
and private facade imports through explicit dependencies/configuration, not by
adding a second agent or broad default tool access. Publish no persona, policy,
credentials or household identifiers. This extraction is **not implemented here**;
it is an exact public-distribution blocker, not a prerequisite for testing an
already-installed compatible private engine.

Remaining live gates require separate approval: trusted production TLS/credential
provisioning, owner-controlled listener replacement, same-entry options and the
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
