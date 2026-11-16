# Native audio: current implementation and offline qualification

The backend-only **0.2.4 recognition-history candidate** is documented in
[native-transcripts.md](native-transcripts.md). Its transcript behavior and new
qualification totals supersede the no-transcript limitation below; it is not
deployed. This page otherwise records the existing native baseline.

This document supersedes the transport conclusions in the historical native-audio
plan, qualification and extraction notes. It describes the candidate, not a
production deployment or a physically qualified voice pipeline.

## Architecture and exact extension boundary

The optional HA entry uses the already-shipped `companion/` package in this fork:

1. HA performs capture, endpointing and half-duplex listening. Its capture STT
   entity buffers bounded PCM, **does not transcribe**, and returns a short-lived,
   entry-local, one-use opaque handle to the conversation integration.
2. The conversation agent consumes the handle and sends the original PCM to
   `NativeClient`, over authenticated, certificate-verified HTTPS/WebSocket.
   Capabilities must match the explicitly selected named Hermes profile before
   audio is dispatched. Physical device/satellite origins accompany the turn.
3. The existing installed `hermes_native_engine` factory runs in that profile's
   genuine PluginContext. `Host.persona()` loads its SOUL, `Host.memory()` initializes
   its actual Mnemosyne provider, `factory.create_engine()` verifies the profile's
   actual SessionDB path, and `Host.dispatch()` uses scoped tool dispatch. The
   finite reviewed policy remains mandatory; origin bindings are checked by the
   companion. This is the existing native model loop, **not** a Whisper transcript
   fed to the ordinary Hermes agent and **not** a new independent conversation app.
4. The native model receives audio; HA receives final text and follow-up metadata.
   HA retains playback/TTS/listening ownership. Piper remains usable. Failure never
   resubmits the recording to the ordinary API or to STT. Explicit text/Whisper/Piper
   is a separate route, not an automatic recovery action.

No custom image, alternate Hermes source tree or core patch is required by this
candidate. Offline tests used the immutable installed official Hermes **0.23.1**,
core commit **3b421578588243f920886e6fe79a6faa87ea026e**. Core module origins were
`/opt/hermes`, not either experimental native-core repository. Only this fork's
optional package and its declared dependencies were installed into an isolated
qualification environment inside this checkout.

**This is compatibility-qualified, not a public Hermes native-engine SDK.** The
ordinary chat endpoint still rejects `input_audio`: installed
`gateway/platforms/api_server.py:437-473` only accepts text/image parts and raises
`unsupported_content_type` for audio. An executed offline test asserts that
boundary without sending a request. General plugin tool dispatch and the
credentialed provider-request API exist; there is no native-engine registration
surface in the installed PluginContext. The existing bridge explicitly accesses
`PluginManager._plugins` in `companion/hermes_native_companion/__main__.py:14-27`;
`Host` also uses manager home/scope and `_plugin_home_scope`. Those are private
compatibility seams, not invented public extension APIs. If a requirement is
**public APIs exclusively**, rather than this already-built, version-qualified
extension-backed engine, that stronger requirement is still blocked by Hermes
core. This change does not conceal that boundary or build another framework.

## Native-path limits (not ordinary-agent parity)

Native replies are final-only: ordinary text streaming is preserved, but the native
path does not stream incremental speech text. Each native turn opens a fresh
provider connection. Previous user audio is neither retained nor reconstructed as
text; replayed context contains bounded assistant replies and quoted tool results,
not the previous spoken user content. Genuine profile/session ownership therefore
does not mean full normal-`AIAgent` conversational-context parity. This candidate
also does not add recognized transcripts. These are explicit limits, not completed
transcript or native-streaming features.

## Safety and preserved behavior

- Native mode is off by default; the original upstream connection/profile forms,
  text streaming, server sessions, room/device prompt context, diagnostics and
  follow-up controls remain in place. Native options add a separate origin/key;
  the normal API key is never forwarded to the companion.
- Native mode requires an explicit named profile (never an implicit `default`).
  Invalid native configuration is rejected before publishing entry state.
- The existing 1 MiB capture limit, HA endpointing/time limits, one-use/expiry,
  bounded concurrency, TLS verification, replay reservation, cancellation and
  uncertain-effect fencing remain intact. No audio-retention feature was added.
- No `input_summary` generation/storage/replay or memory synchronization was
  reintroduced. Legacy synthetic summaries are excluded from replay; model-produced
  descriptions are not labelled as recognized user words. Existing negative tests
  exercise these rules. No private profile identifiers/records/secrets were copied.

## Executed checks

From the fork root:

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -q` | **233 passed** |
| Installed companion/engine suite against official core, below | **73 passed, no skips** |
| Real HA runtime suite, below | **66 passed, no skips**, 5 warnings |
| `git diff --check` | Passed |

The HA environment was **2026.11.1**, pytest plugin **0.13.375**. Its socket and
thread teardown gates remained enabled. The warnings were pytest's pre-imported
`anyio` rewrite notices and official Hermes' positional `re.split` deprecation.
The companion suite also emits expected TLS-handshake diagnostics from deliberately
rejected certificates; these are negative-test output, not a production incident.

The wheel was built/installed as `hermes-ha-native-companion==0.2.4` in
`.native-qualification`. That environment references `/opt/hermes` and its existing
site-packages without installing a separate Hermes checkout. It also has the
package's `[engine]` dependencies and test-only `cryptography`. Its `official-hermes.pth`
contains only the official runtime/site-packages paths. No existing runtime or
production environment was modified.

```bash
HERMES_NATIVE_QUALIFIED_CORE=/opt/hermes \
HERMES_NATIVE_PACKAGED_PYTHON="$PWD/.native-qualification/bin/python" \
.native-qualification/bin/python -m unittest discover -s companion/tests -q

HERMES_NATIVE_REQUIRE_INSTALLED=1 \
HERMES_NATIVE_PACKAGED_PYTHON="$PWD/.native-qualification/bin/python" \
HERMES_NATIVE_TEST_DEPENDENCY_PATHS="$PWD/.native-qualification/lib/python3.14/site-packages:/opt/hermes:/opt/hermes/.venv/lib/python3.14/site-packages" \
/opt/data/environments/ha-runtime-2026.11/bin/python \
  runtime_tests/run_modern.py runtime_tests -q
```

The harness appends dependency paths (it does not process a foreign environment's
`.pth` files), preserving HA's own pinned packages. `HERMES_NATIVE_REQUIRE_INSTALLED=1`
makes a missing installed engine an error instead of silently skipping its case.
The installed-artifact fixture now checks the wheel's actual distribution root,
not the running interpreter's site-packages directory, so real HA can exercise the
installed wheel without mutating its environment.

Coverage includes actual TLS client/server exchange, packaged CLI/factory startup
and shutdown, actual scoped PluginContext and SessionDB, actual memory adapter,
provider-wire synthetic audio/tool rounds, private origin rejection, replay and
uncertain-effect fencing, real HA capture/entry lifecycle, installed-engine
end-to-end history/events, and native failure followed by **explicit** text use.
Only external provider/catalog boundaries and PCM are synthetic. No provider
requests, physical capture/playback or device actions were performed.

## Remaining activation requirements (not executed)

1. Owner approval to deploy this HA candidate and reuse the existing optional
   package/backend lifecycle. Do not run a second owner or replace a container.
2. Confirm the owning named profile's installed native plugin, approved finite
   policy, exact supported memory dependency versions, provider entitlement and
   exclusive lifecycle lock. The ordinary API must remain for explicit text.
3. Configure/verify the existing companion's trusted TLS origin, separate strong
   credential and explicit device/satellite bindings. Select the same named
   profile in the HA entry and opt in to native mode. Secret values belong in
   owner-controlled configuration, never this repository.
4. Select this entry's capture STT and conversation agent in the HA voice pipeline,
   retaining HA endpointing, follow-up policy and Piper playback. Keep an explicit
   Whisper/text/Piper pipeline available rather than automatic audio replay.
5. Separately authorize provider and physical qualification: heard speech,
   persona/memory/session continuity, allowed tools, two-turn wake/listen/playback,
   interruption/unload/failure, and no unintended action. Offline tests do not prove
   those physical/provider outcomes. No deploy, restart or push was performed.
