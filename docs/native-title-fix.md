# Companion 0.2.2: backend-only native session preparation fix

The native engine no longer assigns a room label as a globally unique automatic
session title. Normal origin-based session IDs and the existing room `display_name`
remain unchanged. Existing session titles/rows are not migrated, renamed or deleted.
There is no new title generator, exception suppression or retry.

## Offline qualification

The installed 0.2.1 wheel fails the new regression with the actual official
Hermes SessionDB title uniqueness `ValueError`. The installed 0.2.2 wheel passes:

- Companion suite: 38 tests, no skips, against official Hermes 0.23.1.
- Real Home Assistant 2026.11.1 runtime: 66 tests, no skips (5 existing warnings).
- Integration unit suite: 233 tests.

The new regression populates an old session owning `Native audio — Living Room`,
then completes two distinct native conversations in that same room through the
actual packaged factory, Engine, NativeLoop, SessionDB and memory integration.
Only provider/catalog networks and PCM are synthetic. It checks preserved room
labels, distinct session/origin identity, replay rejection, no semantic summaries,
and no mutation of the old session. Existing permission, cancellation and origin
negative tests remain in the suite.

## Distribution boundary

`companion-v0.2.2` is a **backend-only GitHub prerelease**, deliberately excluded
from stable HA Marketplace integration updates. The Python package version is
`hermes-ha-native-companion==0.2.2`; the wheel is installed in the existing owning
backend environment. This is not an HA component release and must not be installed
through Marketplace. Stable fork tracking remains `v1.4.4-native.1`, whose HA
manifest and all component bytes are unchanged. No existing tag/release is replaced.

Updating an existing backend needs only its approved graceful worker restart under
its existing supervisor. Do not reinstall the plugin shim, restart HA, replace the
Hermes container/image or modify official core for this fix. Keep policy, profile,
credentials, TLS files, pipelines and Piper settings unchanged.

Offline success does not establish a new spoken turn succeeds. Provider/audio,
playback and physical-device qualification require separate explicit authorization.
The final-only/no previous spoken-word replay/no-summary limitations documented in
[native-audio-current.md](native-audio-current.md) still apply.
