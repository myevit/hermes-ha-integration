# Optional native audio: design checkpoint

Base: WolframRavenwolf/hermes-ha-integration main at
`c75290944befdc9b890e5aba2aa70a43bbdbeceb`, MIT. Installed integration
manifest identifies that upstream and version 1.4.3. No contributing guide or
inherited GitHub Actions workflows were present at this revision.

Keep domain, config-entry version, conversation identity, diagnostics, and normal
text path. Add an opt-in STT-slot PCM adapter under the same entry. HA still owns
capture, VAD, its native audio limits, pipeline cancellation and Piper output.
The adapter returns a short-lived, single-use opaque token, never a transcript.
Only this entry's conversation agent consumes it; missing/expired tokens fail
closed and must never be sent to the ordinary text model. Ordinary text continues
to use the upstream API, profile route and session handling unchanged.

The normal Hermes text API has no compatible native-audio endpoint. Use an
optional companion transport with versioned, authenticated capability negotiation
on a separately configured HTTPS origin. Certificate verification is mandatory.
The configured profile must match the companion's advertised profile. Send only
PCM16 mono 16 kHz plus random session/turn identities; no household policy is
published. The profile owner must provide real native inference, memory, session
continuity and its complete normal tool policy. No default-profile fallback,
transcription-to-text delegation, restricted one-device mock, microphone service,
new listen controller, core fork or firmware changes.

Scope checkpoint: the HA adapter and optional `companion/` HTTPS/WSS peer are
implemented. The peer binds to an explicitly installed native-engine plugin
factory; Hermes 0.23.1 has no core native-engine factory SDK. The installed
factory was qualified offline without publishing its private source or policy.
This dependency, physical-origin routing and the actual one-database storage
mismatch remain gates; the transport is not an end-to-end replacement. Native failure never
replays a potentially effectful request through text. Text fallback means ordinary
text/local-STT pipelines remain available, not automatic inference retry.

## Activation and retirement gate

Not deployed. Installation replaces files in the existing domain and needs one
explicitly approved HA Core restart; options reload alone cannot load new platform
code reliably. Native companion lifecycle is independent: only its own service,
not the Hermes gateway, should restart when its binding changes. No new gateway
is required by this design. Do not alter a working pipeline during development.

Back up current integration bytes, entry options and complete pipelines through
supported APIs. Keep the old custom integration and service available alongside
the new optional STT entity until the candidate route is qualified. Preserve the
existing conversation entity/config-entry IDs. Change pipeline STT selection only
through supported pipeline APIs, preserving all other fields and satellite
selectors. Native capture tokens must not go through local intent handling.
Validate that pipeline behavior before switching the preferred route.

Acceptance: upstream text/session/silence regressions; real HA platform import and
setup/unload; authenticated capabilities/profile mismatch; PCM/capture bounds;
single-use/expired tokens; cancellation and server-side replay rejection; correlated
final-only output; explicit follow-up and Piper generation without playback;
profile memory and full tool-policy parity. Provider execution and physical
microphone/speaker tests remain separately approved gates.

After those pass and the user approves the switch: update the selected pipeline,
observe it, then retire the old capture/conversation integration and its dedicated
backend service via their owning lifecycles. Keep a rollback copy and supported
pipeline restoration. Never remove shared policy, tools, persona or session DBs.
An upstream PR is deferred until testing and later approval.
