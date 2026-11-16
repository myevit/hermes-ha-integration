# Fork native release v1.4.4-native.1

This release publishes the optional-native-audio feature from
`dd3df9660cf6c3cc842037d65bd33d796c6cfaaa` as a distinct Marketplace-installable
fork release. Runtime component Python is unchanged from that qualified commit.
Only manifest version, code owner and documentation/issue provenance change.
The integration domain and display name stay unchanged for compatibility.

The existing optional `hermes-ha-native-companion==0.2.1` package is retained;
this release does not replace a Hermes container, image or core. Ordinary text,
HA pipeline ownership and Piper remain available. Native replies are final-only;
recognized transcripts, previous spoken user content and generated input summaries
are not added. Physical/provider qualification remains outstanding. See
[native-audio-current.md](native-audio-current.md) for the exact implemented
boundary and offline qualification.

For Marketplace migration from another repository owning `hermes_conversation`,
back up entry data/options, entity metadata and pipeline/satellite mappings first.
Use supported HA entry removal, old repository uninstall/unregister, explicit
fork release install, user/options flows and registry updates. Entry identity
changes; restore entity IDs and mappings deliberately. Never edit `.storage`
or bypass repository ownership guards.
