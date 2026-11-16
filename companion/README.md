# Optional native-audio companion (experimental)

A real HTTPS/WSS protocol peer for the existing `hermes_conversation` entry. It
wraps an **already installed, explicitly selected, profile-owned native engine**;
it is not another agent, transcription fallback, provider implementation, or HA
integration domain. Ordinary text still uses the unchanged upstream API.

## Optional packaged engine (0.2.2)

See [current qualification and activation requirements](../docs/native-audio-current.md)
for the immutable official-runtime result and the exact private compatibility seam.
Packaging this existing engine is not a claim that Hermes has a public native-audio SDK.

The wheel now includes `hermes_native_engine`: the extracted, already-qualified
Host/Engine/NativeLoop, normal Sessions/MemoryManager/Mnemosyne path, reusable
finite policy/schema library, PCM conversion and licensed subscription provider
subset. It does **not** require private profile modules, backend files or Talk
installation. No second agent, invented Host or alternate session writer exists.
No persona, policy, auth files or bindings are bundled except a clearly fictional,
**unapproved** standard-entity example.

Install into an existing supported Hermes runtime (not HA):

```
python -m pip install 'hermes_ha_native_companion-0.2.2-py3-none-any.whl[engine]'
hermes-ha-native-engine-install --home /path/to/hermes/profiles/voice-example
```

The second command only installs an inert shim. It refuses existing destinations;
it neither enables the plugin, edits config nor starts a service. Explicitly enable
`hermes-ha-native-engine` in that owning profile's `plugins.enabled`. Use its
`create_engine(policy_path, reviewed_switches=[], select_options={})` factory via
`--engine-plugin hermes-ha-native-engine`. Put owner-only JSON factory kwargs in
`--factory-options`. Bindings, reviewed switches and per-target select option enums
must be explicitly reviewed configuration, never wildcards or package defaults.
Existing policy JSON can be used unchanged with the binding-specific switch/select
grants passed at runtime. Changing these grants changes the policy fingerprint.
Read-only policy mode forbids effects rather than hiding a broad dispatcher.

The same generic `Policy`, `Capabilities` and `Host` library can support an owner's
separate text facade without publishing its binding policy or custom tool prefix.
The terminal `finish_turn` belongs only to the native loop, not the text catalog.
No fixed catalog count is a permission boundary: policy and installed native
schemas determine the exact admitted set.

The subscription adapter uses the owning profile's Hermes-signed provider API;
it does not read private auth paths, issue credentials or fall back to default
profile/metred API keys. Standard scoped `HASS_URL`/`HASS_TOKEN` enable the two
finite read-only REST operations; neither has an implicit origin/token. Service
and entity reads use the owning profile's selected MCP. No broad admin grants.

See [license/provenance and supported dependency versions](hermes_native_engine/PROVENANCE.md).
Hermes 0.23.1 has no core native-engine registry. `load_engine()` deliberately uses
a version-qualified PluginManager loaded-module compatibility seam, not a claimed
new core SDK. The public shim supplies `register(ctx)`/`create_engine` and the
actual provider-signing call frame inside its installed, declared-auth directory.

## Standalone lifecycle

Install this directory in the **owning Hermes runtime environment**, not inside
HA. Select the optional public engine extra above or a separately qualified engine.
No production install/restart is performed by this repository's tests.

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

One credential defaults to one explicit device/satellite principal. An optional
owner-only `--bindings-file` selects a finite JSON list of `[device_id, satellite_id]`
pairs (at most 64, including the primary pair), each checked against the existing
engine policy. No wildcard or automatic whole-policy grant is accepted. The HA
adapter sends registry-correlated `origin` device/satellite/area metadata. The
bridge rejects unknown pairs and mismatched policy areas. Multi-device endpoints
require origin; only a single-principal endpoint accepts legacy starts without it.
The credential authenticates HA, not independent satellite hardware. Keep it scoped
to the intended HA entry. The complete engine policy is reused, never published.

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

The protocol cases use real verified loopback TLS and the actual HA client source.
The public-factory cases require a supported Hermes installation plus the wheel's
`[engine]` extra. They exercise its installed shim through the genuine loader,
factory, Engine, Host, PluginContext, SessionDB, MemoryManager and Mnemosyne in a
disposable named profile. Only provider and MCP **network** boundaries are synthetic.
No private plugin/profile paths or `PYTHONPATH` dependencies are required. Set
`HERMES_NATIVE_PACKAGED_PYTHON` to the clean wheel interpreter to require artifact
imports and exercise the actual CLI, discovery, TLS turn, lock and shutdown.
Negative SDK tests also prove the declared-auth shim cannot sign a foreign origin.
Policy tests verify no default switch/select grants or dangerous generic services.

See [qualification](../docs/native-audio-qualification.md) for executed versions,
HA fixture compatibility, separate normal session/memory storage and remaining
live approval gates. No real provider, microphone, playback or device test is
implied. The security review remains partial, not a clean security stamp.
