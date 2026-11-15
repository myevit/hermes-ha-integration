# Native-audio qualification checkpoint

Status: **Implemented protocol peer + authentic installed-engine bridge; NOT yet
an approved/deployable replacement for the existing backend.**

## Executed offline

| Gate | Result |
|---|---|
| Existing unit suite, `python -m unittest discover -s tests -t . -q` | 229 passed |
| Companion TLS/factory suite, `python -m unittest discover -s companion/tests -v` with explicit installed dependency | 14 passed (10 protocol + 4 installed-engine) |
| Real HA 2026.9.4, `python runtime_tests/run_modern.py runtime_tests -q`, with installed-factory environment | 35 passed |
| Real HA **2026.11.1**, same runtime suite and installed factory | **35 passed** |
| Wheel + source distribution, `uv build companion` | Built successfully; CLI `--help` executed |
| Real provider/cloud, microphone, playback, device control | NOT RUN |
| Production installation, restart, configuration/pipeline changes, decommission | NOT AUTHORIZED / NOT RUN |

Exact interpreters: Hermes host **Python 3.14.9**, **Hermes 0.23.1**, aiohttp
**3.14.5**. Both HA fixtures use **Python 3.14.6**. HA 2026.9.4 uses test plugin
**0.13.367**; HA 2026.11.1 uses plugin **0.13.375** and pytest **9.0.3**.
Installed memory dependency qualified here: **mnemosyne-hermes 0.5.0** (real
provider and `MemoryManager`, not a memory stub).

The latest published HA pytest plugin pins HA 2026.10.4, not 2026.11.1. The exact
executed 2026.11 fixture environment is `requirements-test-ha-current.txt`; install
that complete lock into a disposable Python 3.14 venv with `--no-deps`, then use
`runtime_tests/run_modern.py`. Its test-only compatibility adapter preloads HA
before HTTPX plugins and replaces the removed global logger-overwrite cleanup
hook with resetting the logging class. HA 2026.11 keeps those overrides in a
per-class closure. This does not patch the integration or production HA. The
older fixture remains separately pinned in `requirements-test-ha-modern.txt`.

## What is real versus synthetic

The protocol tests use actual verified loopback HTTPS/WSS, certificate rejection,
bearer auth, the actual HA `NativeClient`, strict capability/profile negotiation,
bounded PCM, correlated final output, disconnect/explicit cancellation, failure
after an effect boundary, and durable duplicate-turn rejection even with changed
session or fresh journal connection. No insecure TLS override is used.

The installed-engine tests use a **separately installed** plugin's actual Hermes
loader and `register(ctx)`/`create_engine(...)`, real Host/Engine/NativeLoop,
authentic `PluginContext`, finite registered read catalog, actual admission
policy, real profile-local SessionDB, real MemoryManager and real Mnemosyne
provider. The disposable home has the dependency's genuine profile identity,
not a relabelled default profile. Only provider and MCP **network boundaries** are
synthetic. Persona, policy and PCM are explicitly synthetic fixture inputs; no
production config, session DB, memory or household policy is opened by tests.

Actual HA tests now exercise the same-entry STT capture/token, conversation
entity, actual TLS client/companion/installed engine, two-turn session/history,
follow-up flag, activity start/completion, zero residual active requests and
setup/unload without lingering heartbeat timers. A real delayed-capture test
passes after 10.05 seconds: the private 10-second capture watchdog was removed;
HA's 60-second capture ceiling and the independent 1 MiB byte budget apply.
Existing text/session/silence/diagnostics/naming regression tests remain intact.

Provider catalog mismatch is refused before sending PCM. Cancellation while
awaiting final tool-output acknowledgement yields interrupted session metadata
and no successful final/semantic-summary row. Two native utterances preserve
one conversation session and project its semantic history into the next
provider conversation. Real memory identity and temporary-home isolation are
asserted across both turns.

## Explicit hard gaps — do not call these complete

1. **No core native-engine SDK / packaged generic inference engine.** Official
   plugin documentation and installed Hermes 0.23.1 expose PluginContext, not a
   native-engine registry. The peer is fully implemented but still requires an
   independently installed compatible native-engine plugin. The small loader
   seam accesses the manager's loaded-module map, explicitly version-qualified;
   it is not advertised as a stable core factory API. No private implementation,
   persona, tool facade or household binding has been published.
2. **Requested one-database storage is NOT present in this actual runtime.** The
   genuine factory returned `hermes_state.SessionDB`; installed-source lookup
   found no `MnemosyneSessionDB`. The real memory provider used a separate
   profile-local Beam database. Qualification prints `ACTUAL_ONE_DB False`.
   The companion's replay journal shares the engine's existing database and
   never fabricates session rows, but cannot honestly turn that installed
   two-store architecture into one-db qualification. Resolve the owning
   runtime's supported SessionDB/memory configuration before migration.
3. **Physical-origin and multi-device policy parity remain unqualified.** Version
   one sends session/turn IDs, not physical device identity. The credential is
   explicitly bound to one finite device/satellite principal; sharing it across
   devices is unsupported. The transport does not replace the engine's complete
   policy, but that alone does not establish full household route parity.
4. Provider inference/real acknowledgements, pipeline local-intent bypass, Piper
   generation, physical capture/playback and actual activation remain separately
   approved gates. Synthetic provider network events are not cloud qualification.

## Existing service owner / retirement gate

Read-only current-process ancestry identified the live native listener beneath
its recovery supervisor and **s6-supervise native-audio**. The listener and
recovery supervisor run as the non-root application uid; s6 is the lifecycle
owner. A direct s6 status probe was permission-denied. Current PID/command/uid
receipt is kept locally, not published with private addresses, profile paths,
entry IDs or household policy. No service was restarted or changed.

The candidate must **replace that listener**, not add a third backend. Standalone
startup requires its existing lifecycle lock, explicit owning profile/plugin,
managed credential, finite binding and verified TLS. Shutdown cancels transport
work and waits for the engine's uncertain pending effects before closing its DB
and releasing the process/lock. Do not mint a different lock to bypass the owner.

After resolving all gaps and explicit lifecycle/HA restart/route-switch approval:
back up current integration bytes, entry options and pipeline records; retain
conversation identity and ordinary text mode; install into the same integration
domain; switch only through supported HA APIs; observe provider/physical gates;
then retire the old capture integration and dedicated listener through their
actual owners. Keep rollback material. Never remove shared policy, tools,
persona or session/memory databases. No upstream PR until later approval.

No Actions workflows, CI secrets or administrative permissions were added.
Private raw logs and receipts are deliberately excluded from the public fork.
