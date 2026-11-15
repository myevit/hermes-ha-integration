# Native-audio checkpoint qualification

Status: **HA-side experimental candidate; NOT a deployable backend replacement.**

Executed locally with Python 3.14:

| Gate | Result |
|---|---|
| `python -m unittest discover -s tests -t . -q` | 229 passed |
| Real HA upstream harness, `pytest -c pytest.ini -q` | 32 passed on HA 2026.9.4 |
| Native boundary unit subset | 9 passed, included above |
| Native real-HA subset | 4 passed, included above |
| Production installed HA version discovered read-only | 2026.11.1; not modified |
| Native real provider, physical audio, playback | NOT RUN |
| Actual authenticated HTTPS companion interoperability | BLOCKED: companion not implemented |
| Server replay rejection / disconnect cancels inference | Contract required; NOT qualified on real server |
| Endpoint identity/session correlation and full profile-policy parity | Remaining qualification gate |
| Real HA 2026.11.1 candidate setup | NOT RUN |
| Migration and decommission | NOT AUTHORIZED / NOT RUN |

Real-HA tests exercise optional STT platform registration, capture, native result
handoff into the existing conversation entity, follow-up flag, replay refusal,
text API non-dispatch, invalid PCM and unload. The native inference method is
mocked in this suite; protocol tests use a synthetic peer. Those are not claims of
native model success. Existing upstream runtime tests retain text, diagnostics,
silence, naming and lifecycle coverage. Unit tests intentionally inject failures
and print synthetic exception logs; raw logs are not published here.

No inherited Actions workflows were found, no new workflows added. No secrets,
private profile source, household binding or production receipts belong in this
fork. No upstream PR, production writes, service restarts, provider calls or
device changes were made.

## Resume here

1. Review companion scope against upstream. Implement an optional house-agnostic
   authenticated service binding to the genuine profile-owned native engine; do
   not publish the existing private backend wholesale. It must implement
   `GET /v1/native/capabilities` and `WSS /v1/native` used by `native.py`.
2. Qualify real TLS/auth, redirects, capability mismatch, bounded upload,
   duplicate turns, disconnect cancellation, endpoint/profile/session continuity,
   complete tool-policy parity and normal memory. Server must atomically reserve
   turn IDs before inference; client non-retry alone is not server replay defense.
3. Exercise current installed HA version and pipeline local-intent bypass, Piper
   output and profile continuity. No microphone/playback without approval.
4. Follow the migration/rollback plan only after gates pass and explicit restart
   and route-switch approval. Keep the old route operational until then.
