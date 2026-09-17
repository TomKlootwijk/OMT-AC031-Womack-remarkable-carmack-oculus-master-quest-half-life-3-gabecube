# R20 radio packet studio

The user requested analysis of their physical POCO session, app enhancement,
and packet decoding, choosing PCAPdroid integration for this phone's traffic.
Preserve R19 and old releases unchanged. Commit/push validated development
stages and update the full PDF formalization. Keep the same Android package
and signing key so upgrades retain sessions. Never uninstall the logger to
upgrade. Private physical captures and derived identifying data belong only
under private/ or sessions/ and MUST NOT enter Git or public release archives.

Wi-Fi information elements are Android-exposed beacon fields, not full frames.
PCAPdroid observes this phone's routed IP traffic, not arbitrary nearby cellular
subscribers. Preserve raw bytes, clocks, provenance, encryption boundaries,
unsupported protocols, truncation and decoding errors. Never invent decrypted
payloads or synthesize packet captures from radio-power measurements.

Use a separate user-started PCAPdroid app for capture; do not build a partial
VPN forwarding implementation. Preserve device state and captured evidence
when updating. Public examples must be synthetic or explicitly emulator data.
