# Native recognition history: 0.2.3 candidate

**Offline-qualified only; not deployed or released.** The approved configuration
probe accepted gpt-realtime-2.1 with PCM24k and gpt-4o-transcribe input
transcription on the existing subscription connection. It sent no audio and
created no response. Real ASR execution, latency and live household history remain
untested; configuration acceptance does not establish entitlement or cost.

## Behavior

The existing single native websocket requests optional input recognition. Original
PCM remains the sole current deciding input, appended and committed once. There is
no summary, external STT endpoint, alternate ASR model, paid fallback or second
inference. Existing native assistant/tool history remains unchanged.

Only terminal input_audio_transcription.completed text matching the exact
input_audio_buffer.committed.item_id and integer content_index zero can become
words. At most eight terminal events of at most 12,000 characters each are buffered
before commitment. Foreign items/indices, deltas and missing commit identity cannot
be guessed into transcripts. First matching terminal event wins; duplicates and
conflicts cannot append or merge records.

One recognition system row per admitted/started turn is appended with ordinary
visible content through existing SessionDB.append_message, plus recognition
metadata. It is labelled **Speech recognition (may contain errors; not guaranteed
verbatim)**. Provider failure, empty/oversized text, unavailable configuration,
late events and cancellation use fixed unavailable labels, never invented words
or provider error details. Recognition can remain available when later native
operations are interrupted. Existing audio occurrence, tool results, final answer
and interruption notices are separate rows. Recognition text is deliberately
retained in history; audio and provider error payloads are not retained or logged.

Optional configuration rejection tied to this update's event ID retries only
configuration, once, on the same connection with recognition disabled before
audio. Ignored configuration also degrades to unavailable. An unrequested model
is disabled before audio; refusal to disable fails closed under existing privacy
constraints. Unrelated native/provider errors are not suppressed.

The shared receive boundary filters recognition before native response and
acknowledgement event counters. Discarded deltas and foreign-item recognition do
not spend the existing 400-event native budgets. Recognition has its own **4,096
events per turn** flood limit (including discarded events), with cooperative
cancellation/deadline checkpoints every 64 events even when socket reads are
immediately ready. Crossing that separate malicious-flood bound fails closed;
it is not an unlimited promise to drain ASR. The existing eight-terminal buffer,
text bounds, overall deadline and post-final grace remain unchanged.

The existing event loop consumes recognition without a background reader. After
a valid native final result, it waits at most **750 ms**, within the existing
45-second deadline with a 50 ms margin. The recognition record precedes final
assistant persistence. Missing/slow recognition becomes late, without revision,
background task or next-turn wait. Post-final socket errors do not revoke a valid
answer. Cancellation propagates immediately and releases the normal lock/socket.
This deliberately trades occasionally missing transcripts for bounded latency.

Native history excludes all recognition records and legacy generated semantic
derivatives. Recognized words are not sent to model history or memory learning.
The working same-room/title fix is preserved.

## Supported activation: separate approval required

The existing backend-only wheel lifecycle, established before implementation from
native-title-fix.md, supports exact reviewed wheel installation in the existing
owning backend environment followed by one graceful worker restart under its
existing supervisor. No dependency churn, plugin-shim reinstall, HA restart,
Marketplace update, profile changes, container replacement, core patch, new
service, extra worker or Desktop change is required. Parent review and explicit
owner approval gate installation, restart and live speech testing. None occurred.

## Offline results

- Integration unit suite: **233 passed**.
- Installed 0.2.3 companion on official Hermes 0.23.1: **70 passed, no skips**,
  including **32 recognition regressions** (eight added after independent review).
- Real HA 2026.11.1 runtime: **66 passed, no skips**, five warnings; installed-wheel
  requirement and socket/thread teardown gates remain enabled.
- Real SessionDB and the actual REST history handler: passed.
- Official Desktop toChatMessages hydration for REST and gateway display history:
  passed. The record becomes exactly one visible system text bubble before the
  final assistant answer. Hidden/metadata-only negative controls stay invisible.

Tests cover exact/wrong/early items, wrong index, repeated/conflicting events,
ASR failure, invalid/oversized text, deltas, configuration refusal/ignored/alternate
model, late/never events, deadline/cancel/socket failures, native interruption,
legacy and two-turn no-feedback, original resampled PCM and one commit/response.
Existing scoped tools, persona, isolation, permissions, limits and title tests
remain in the full suites. Only provider/catalog network and PCM are synthetic;
packaged factory, SessionDB and memory adapter remain real.

REST qualification invokes the actual handler behind its existing access-check
decorator with a synthetic request and real test DB. It opens no REST listener.
The actual gateway display_projection and REST output feed the official Desktop
hydration and real parts/tool-parts/generated-images helpers. Unrelated UI imports
are throw-on-use seams, none invoked for these text rows. This is an offline
hydration check, not a claim of a running Desktop/browser or household turn.

Commands for the full suites remain in native-audio-current.md. The extra
companion test module is test_transcripts.py; verify_history_rendering.mjs accepts
a private history receipt and output bundle path, using the existing esbuild
module and official Desktop source selected through environment variables. It
does not install packages or alter Desktop source. Private logs, synthetic
history/hydration receipts and frozen wheel are kept outside the repo under
/opt/data/reports/ha-native-transcript-candidate/.

Companion tests emitted resource/deprecation warnings while importing official
core; the tests passed with no disabled teardown gate. No live provider request,
audio upload, physical microphone use, deployment, push, publication, configuration
change or production restart was performed.
