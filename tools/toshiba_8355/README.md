# 8355.json (ToshibaJDX, ZS06 厨房・洗い場・食器棚・食堂)

Copy of the file deployed on the live Home Assistant (`custom_components/smartir/custom_codes/climate/8355.json`).

- 2026-11-15: `supportedModels` set to `WH-RA05JJ` (was `SRK20ZSA-W`; metadata only). Codes unchanged.
- Check of all 133 codes (2026-11-16): two identical frames per code, 10 bytes (OFF: 9 bytes); every code follows
  `4f b0 20 df 90 [rev4(temp-17)] [mode|fan] 00 0c [xor of bytes 0..8]` (heat c0 / cool 80; fan auto 0, Silent 4, 1 2, 2 1, 3 5, 4 3);
  XOR checksum correct in all 132 + OFF. No bit-level defects.
- Pulse timing: bit periods are consistent, but in about 17 second frames the individual pulse lengths jitter
  (mark 480-660 us vs. typical 590 us, with the space compensating). Left unchanged (unlike 8356, where six codes were re-timed).
- Not verified against real remote captures or the air conditioner.
