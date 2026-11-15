# 8355.json (ToshibaJDX, ZS06 厨房・洗い場・食器棚・食堂)

Copy of the file deployed on the live Home Assistant (`custom_components/smartir/custom_codes/climate/8355.json`).

- 2026-11-15: `supportedModels` set to `WH-RA05JJ` (was `SRK20ZSA-W`; metadata only). Codes unchanged.
- Check of all 133 codes (2026-11-16): two identical frames per code, 10 bytes (OFF: 9 bytes); every code follows
  `4f b0 20 df 90 [rev4(temp-17)] [mode|fan] 00 0c [xor of bytes 0..8]` (heat c0 / cool 80; fan auto 0, Silent 4, 1 2, 2 1, 3 5, 4 3);
  XOR checksum correct in all 132 + OFF. No bit-level defects.
- Pulse timing: in 24 codes the individual pulse lengths jittered (mark 480-660 us vs. typical 590 us, space compensating).
  2026-11-16: those 24 codes were re-timed to the typical values (header 4441/4441, mark 591, zero 492, one 1589, gap 5447 us); bits unchanged
  (all 133 codes re-checked: bits identical, XOR checksum ok). Re-timed: heat auto 18/20/26, Silent 20/21/22/23/25, 1 24, 2 22, 3 27/28, 4 26/27;
  cool auto 18/25, Silent 18/20/22/23, 1 21/23/25, 2 18. Backup of the previous file: `custom_components_back/8355-before-retime-20261116.json` on the HA.
- Not verified against real remote captures or the air conditioner.
