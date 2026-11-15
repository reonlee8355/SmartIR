# 8356.json (ToshibaUR, ZS06 彦名)

Copy of the file deployed on the live Home Assistant (`custom_components/smartir/custom_codes/climate/8356.json`).

- 2026-11-15: six codes whose pulse timings were off were re-timed (bit content unchanged): heat auto 24/25/27, heat fan1 18, cool fan1 20, cool fan2 26.
- 2026-11-15: `supportedModels` set to `WH-UB01UJ` (was `SRK20ZSA-W`; metadata only).
- Verified against 11 real remote captures (all bytes match). Not verified against the air conditioner itself.
