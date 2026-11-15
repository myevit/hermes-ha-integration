# Provenance and supported boundary

* Host, finite Policy/Capabilities, Sessions, NativeLoop and Engine: extracted
  with the owner's explicit publication authorization from the previously
  qualified owner-written implementation; distributed under this repository's MIT
  license. No owner policy/persona/auth/configuration is included. The PCM ratecv
  conversion is the same qualified four-line conversion, not a copied backend.
* `talk_wire.py::parse_client_secret` and its endpoint constants are a minimal
  subset of TheSmokeDev/hermes-talk, commit
  `790f6d283d4720302eda21f9086d4fc01be3ec0a`, `talk_wire.py`.
  `provider.py` adapts its `talk_auth.py::codex_request` signing flow, subscription
  only. Original MIT notice is retained verbatim in `TALK-LICENSE` in the wheel.
  Source: https://github.com/TheSmokeDev/hermes-talk/tree/790f6d283d4720302eda21f9086d4fc01be3ec0a
* Hermes and Mnemosyne are installed dependencies, not vendored code. Their
  distributions retain their respective licenses. `audioop-lts` supplies the
  removed stdlib API on Python 3.13+; no codec implementation is copied here.

Qualified against Hermes 0.23.1 installed plugin/credential interfaces and Python
3.14.9. The core deliberately refuses non-editable wheel builds: install Hermes
using its supported installer/container/Nix or editable developer installation;
this package does not distribute or claim to replace it. The companion/engine
itself is an ordinary tested wheel. PluginManager loaded-module access and
profile scope are explicitly version-qualified compatibility seams, not a core
native-engine SDK.

Memory dependencies are deliberately exact: mnemosyne-memory 3.15.1 and the
maintained mnemosyne-hermes 0.7.1 adapter. The PyPI adapter named 3.1.0 is older
and did not preserve owning-home storage across repeated isolated-profile tests;
version ordering is not a compatibility guarantee. Do not upgrade by choosing the
numerically largest adapter release. No private/vendor adapter is required.

The license check confirmed MIT permission and preserved attribution for the
copied Talk subset; this is not legal advice or a full third-party license audit.
Security review remains partial; passing offline checks is not certification.
