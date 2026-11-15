#!/usr/bin/env python3
"""Generate SmartIR device JSON (Tuya/ZS06 IR codes) for the Daikin BRC4C105 remote
(ceiling cassette; installed in the 大広間).

Protocol (decoded from real captures of the remote, see captures.json; 22 bytes in two frames,
the same length/header family as IRremoteESP8266's DAIKIN176 and the same field layout as the
BRC4L101 for mode/temperature/fan). Byte indexes are 0-based.
  frame 1 (7 bytes)  : 11 da 17 18 04 00 1e                          (constant)
  frame 2 (15 bytes) :
     [0:4]  11 da 17 18   constant
     [4]    00
     [5]    73            constant in all captures
     [6]    00            constant in all captures
     [7]    mode<<4 | power      cool=2 heat=1, power 1=on 0=off
     [8],[9] 00 00        constant in all captures
     [10]   (temp - tmin(mode)) * 2 + 16     tmin: cool=20, heat=15 (the remote's lower limits)
     [11]   fan<<4 | swing     fan value: 弱=1 強=3 急速=5 (SmartIR names 1, 2, 3; this remote has no auto fan)
                               swing nibble: swing=5 auto=6
     [12]   00
     [13]   20
     [14]   sum of bytes 0..13 (mod 256)
  frame 1 checksum: last byte = sum of the previous bytes (mod 256).
OFF keeps the rest of the state of the last mode (power bit cleared), like the BRC4L101.
"""
import base64, json, struct, sys

FRAME1 = bytes([0x11, 0xDA, 0x17, 0x18, 0x04, 0x00, 0x1E])
assert FRAME1[-1] == sum(FRAME1[:-1]) & 255
MODES = {"heat": 1, "cool": 2}
TMIN = {"heat": 15, "cool": 20}          # remote's lower limit per mode
FANS = {"1": 1, "2": 3, "3": 5}   # SmartIR name -> remote value: 1=弱 2=強 3=急速 (no auto fan)
SWINGS = {"auto": 6, "swing": 5}

# timings (us): means of the real captures (7 captures, 14 frames)
HDR_M, HDR_S = 5089, 2140
MARK, ZERO, ONE = 410, 673, 1761
GAP = 29524


def frame2(power, mode, temp, fan, swing):
    b = bytearray(15)
    b[0:4] = bytes([0x11, 0xDA, 0x17, 0x18])
    b[5] = 0x73
    b[7] = (MODES[mode] << 4) | (1 if power else 0)
    b[10] = (temp - TMIN[mode]) * 2 + 16
    b[11] = (FANS[fan] << 4) | SWINGS[swing]
    b[13] = 0x20
    b[14] = sum(b[:14]) & 255
    return bytes(b)


def frame_pulses(data):
    p = [HDR_M, HDR_S]
    for byte in data:
        for i in range(8):
            p += [MARK, ONE if (byte >> i) & 1 else ZERO]
    p.append(MARK)  # stop mark
    return p


def pulses(f2):
    return frame_pulses(FRAME1) + [GAP] + frame_pulses(f2)


def compress(data):
    out = bytearray(); lit = bytearray(); i = 0; n = len(data); tbl = {}
    def flush():
        nonlocal lit
        while lit:
            ch = lit[:32]; out.append(len(ch) - 1); out.extend(ch); lit = lit[32:]
    while i < n:
        best = bd = 0
        if i + 2 < n:
            key = bytes(data[i:i + 3]); j = tbl.get(key)
            if j is not None and i - j <= 8192:
                l = 0
                while i + l < n and data[j + l] == data[i + l] and l < 264: l += 1
                if l >= 3: best, bd = l, i - j
            tbl[key] = i
        if best:
            flush(); L = best - 2; D = bd - 1
            if L < 7: out.append((L << 5) | (D >> 8))
            else: out.append((7 << 5) | (D >> 8)); out.append(L - 7)
            out.append(D & 255)
            for k in range(i + 1, i + best):
                if k + 2 < n: tbl[bytes(data[k:k + 3])] = k
            i += best
        else:
            lit.append(data[i]); i += 1
    flush(); return bytes(out)


def decompress(b):
    out = bytearray(); i = 0
    while i < len(b):
        h = b[i]; i += 1; L = h >> 5; D = h & 31
        if not L: out += b[i:i + D + 1]; i += D + 1
        else:
            if L == 7: L += b[i]; i += 1
            L += 2; D = (D << 8) + b[i] + 1; i += 1
            for _ in range(L): out.append(out[-D])
    return bytes(out)


def encode(f2):
    p = pulses(f2)
    return base64.b64encode(compress(struct.pack("<%dH" % len(p), *p))).decode()


def decode_frames(code):
    """Return [frame1_bytes, frame2_bytes] from a Tuya code (header 4500-5600us, space>1200us = 1)."""
    r = decompress(base64.b64decode(code)); p = list(struct.unpack("<%dH" % (len(r) // 2), r))
    idx = [i for i, x in enumerate(p) if x > 20000]
    parts = []; s = 0
    for i in idx + [len(p)]:
        parts.append(p[s:i]); s = i + 1
    out = []
    for f in parts:
        h = [i for i, x in enumerate(f) if 4500 < x < 5600][0]
        body = f[h + 2:]
        bits = "".join("1" if body[k + 1] > 1200 else "0" for k in range(0, len(body) - 1, 2))
        out.append(bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits) - 7, 8)))
    return out


def build(tmin=20, tmax=30):
    cmds = {}
    for mode in MODES:
        cmds[mode] = {}
        for fan in FANS:
            cmds[mode][fan] = {}
            for sw in SWINGS:
                cmds[mode][fan][sw] = {str(t): encode(frame2(True, mode, t, fan, sw)) for t in range(tmin, tmax + 1)}
    cmds["off_heat"] = encode(frame2(False, "heat", 25, "1", "swing"))
    cmds["off_cool"] = encode(frame2(False, "cool", 25, "1", "swing"))
    return {
        "manufacturer": "Daikin",
        "supportedModels": ["BRC4C105"],
        "supportedController": "MQTT",
        "commandsEncoding": "Raw",
        "minTemperature": tmin,
        "maxTemperature": tmax,
        "precision": 1,
        "temperatureUnit": "C",
        "operationModes": ["cool", "heat"],
        "fanModes": list(FANS),
        "swingModes": list(SWINGS),
        "commands": cmds,
    }


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "8478.json"
    d = build()
    json.dump(d, open(out, "w"), ensure_ascii=False, indent=2)
    print("wrote", out)
