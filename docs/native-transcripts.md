# Native recognition history: 0.2.4 candidate

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

One recognition row per admitted/started turn is appended with ordinary visible
content through existing SessionDB.append_message, plus recognition metadata. It is
labelled **Speech recognition (may contain errors; not guaranteed verbatim)**.

**A successful recognition row is persisted on the ordinary `user` role**, so the
unmodified Desktop paints it with the standard human-message bubble (right-aligned
card, conversation text size) instead of the 0.6875rem, low-contrast, centred
system line that made real recognized words nearly invisible. The row is still not
a user turn: no edit affordance is implied by the backend, the text is a labelled
recognition receipt, and the ordinary user-bubble clamp applies exactly as it does
to a long typed prompt (measured below).

Failure, empty/oversized text, unavailable configuration, late events and
cancellation keep the **`system`** role with fixed unavailable labels, never
invented words or provider error details. Recognition can remain available when
later native operations are interrupted; that row stays a `user` row because the
words were genuinely recognized. Existing audio occurrence, tool results, final
answer and interruption notices are separate rows. Recognition text is deliberately
retained in history; audio and provider error payloads are not retained or logged.
Metadata (`turn_id`, `kind=speech_recognition`, `status`, `recognition_model`,
`input_item_id`, `audio_retained: false`, `not_guaranteed_verbatim: true`,
`history_replay: false`) is unchanged by the role choice.

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
The wheel version is **0.2.4**; the version bump only makes a later approved
activation unambiguous and changes no behavior beyond the row role above.

## Offline results

- Integration unit suite: **233 passed**.
- Installed 0.2.4 companion on official Hermes 0.23.1: **73 passed, no skips**,
  including **35 recognition regressions** (three added with this correction).
- Real HA 2026.11.1 runtime: **66 passed, no skips**, five warnings; installed-wheel
  requirement and socket/thread teardown gates remain enabled.
- Real SessionDB and the actual REST history handler: passed, over the **full row
  set** (contentless native-audio receipt, tool call/result rows, recognition row,
  final answer and interruption notice), for success, available-after-native-
  interruption, failed, unavailable, late and interrupted turns.
- Official Desktop hydration for REST and gateway display history: passed for all
  seven surfaces. The words row hydrates to exactly one visible user bubble before
  the final assistant answer; the contentless audio receipt stays invisible, so it
  cannot produce a second user bubble. Hidden/metadata-only negative controls stay
  invisible.
- Real-browser visual qualification of the **unmodified** Desktop components and
  the **compiled** Desktop stylesheet (dark theme): passed for wide (900×720) and
  narrow (360×720) viewports on every surface, including a pre-change baseline
  fixture that reproduces the reported defect.

### Visual qualification detail

`companion/tests/visual/verify_recognition_visual.mjs` builds a browser bundle of
the real `UserMessage`/`SystemMessage`/`AssistantMessage` components, feeds them the
real REST/gateway rows through the real `toChatMessages` + `toRuntimeMessage`, and
paints them in Chromium with the real `styles.css` compiled by the real Tailwind
Node API. It adds no product UI: it only mounts the unmodified components inside the
same row wrappers `ThreadMessageList` builds. `@/themes/context` is imported for its
own boot paint, so the app's real dark palette applies.

Measured (deviceScaleFactor 2, dark):

| Surface | Role | Font | Lines painted | Row text |
| --- | --- | --- | --- | --- |
| success / available-after-interruption | `user` | 13px (conversation size) | 2/2 wide, 3/3 narrow | all words |
| long non-Latin utterance | `user` | 13px | 5 of 15 wide, 5 of 39 narrow | full 1,238 chars in the row |
| failed / unavailable / late / interrupted | `system` | 11px | all | fixed machine label |
| pre-change baseline (same words, `system`) | `system` | 11px | all | all words, faint |

The long-utterance row inherits the app's standard human-bubble clamp
(`.sticky-human-clamp`, `max-height: calc(4 * 1.3 * conversation-text-font-size)`,
soft mask fade). That is the same treatment any long typed prompt gets and is
**not** changed here: the full text stays in the row and in history, and the
standard affordances (click to open the edit composer on desktop, the read-only
expander, or the gateway history) show all of it. No wording or position change was
made, because reordering the label would hide the uncertainty caveat instead and
would alter the established label contract. This is recorded as a residual, owner-
visible limitation rather than fixed silently.

Line counts come from hit-testing every line box of the row's text node, so a
clamped or covered line is counted as unpainted instead of assumed visible.

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
hydration check plus a real-browser paint check, not a claim of a running Desktop
session against a household turn.

Commands for the full suites remain in native-audio-current.md. The extra
companion test module is test_transcripts.py; verify_history_rendering.mjs accepts a
private history receipt and output bundle path, using the existing esbuild module and
official Desktop source selected through environment variables. The visual harness
borrows the dependency tree of an existing local checkout and installs nothing;
the official `/opt/hermes` install is never written. Private logs, synthetic
history/hydration/visual receipts and the frozen wheel are kept outside the repo
under /opt/data/reports/ha-native-recognition-display-candidate/.

Companion tests emitted resource/deprecation warnings while importing official
core; the tests passed with no disabled teardown gate. No live provider request,
audio upload, physical microphone use, deployment, push, publication, configuration
change or production restart was performed.
