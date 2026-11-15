#!/usr/bin/env python3
"""Generate SmartIR device JSON (Tuya/ZS06 IR codes) for the Daikin ARC472A142 remote
(wall/ceiling unit in the ロビー). Needs the fork's horizontal swing support (custom.2).

Protocol (decoded from real captures of the remote, see captures.json; two frames of 20 and 19 bytes,
same family as the ARC476A2). Byte indexes are 0-based.
  frame 1 (20 bytes): 11 da 27 00 02 [5] 44|c4 00 20 [9] 02 [11] [12] [13] d2 e0 10 24 00 [19]
     [5]   a counter-like byte that changes slowly between captures; not part of the state -> constant 0x30
     [6]   0x44 on, 0xc4 off
     [9]   0x0e cool, 0x10 heat, 0x02 off
     [11]  0x00 on, 0x80 off
     [12]  vertical swing: high nibble (swing=f, auto=e, position n=n), low nibble 1
     [13]  horizontal swing: swing=0x1f, auto=0x1e, position n=0x08+n (1,3,5 captured; 2,4 interpolated)
     [19]  sum of bytes 0..18 (mod 256)
  frame 2 (19 bytes): 11 da 27 00 00 [5] [6] 00 [8] 00 00 06 60 00 02 c7 20 24 [18]
     [5]   mode<<4 | power: cool on 0x39, heat on 0x49, cool off 0x38, heat off 0x48
     [6]   temperature * 2 (0.5 degree steps)
     [8]   fan<<4: auto=0xa quiet=0xb 1=3 5=7 (2,3,4 = 4,5,6 interpolated)
     [18]  sum of bytes 0..17 (mod 256)
OFF keeps the rest of the state (power bit cleared; frame 1 [6],[9],[11] differ).
Preamble/timings are the means of the 19 real captures (the ZS06 reports the preamble as 2 long pulses).
"""
import base64, json, struct, sys

MODES = {"cool": 0x30, "heat": 0x40}
F1_MODE = {"cool": 0x0E, "heat": 0x10}
FANS = {"auto": 0xA, "quiet": 0xB, "1": 3, "2": 4, "3": 5, "4": 6, "5": 7}
VSWING = {"auto": 0xE, "swing": 0xF, **{str(n): n for n in range(1, 7)}}
HSWING = {"auto": 0x1E, "swing": 0x1F, **{str(n): 0x08 + n for n in range(1, 6)}}
COUNTER = 0x30

PRE = [10060, 25285]
HDR_M, HDR_S = 3508, 1731
MARK, ZERO, ONE = 441, 433, 1298
GAP = 35347


def frame1(power, mode, vswing, hswing):
    b = bytearray([0x11, 0xDA, 0x27, 0x00, 0x02, COUNTER, 0x44, 0x00, 0x20, 0, 0x02, 0, 0, 0,
                   0xD2, 0xE0, 0x10, 0x24, 0x00, 0])
    if power:
        b[9] = F1_MODE[mode]
    else:
        b[6], b[9], b[11] = 0xC4, 0x02, 0x80
    b[12] = (VSWING[vswing] << 4) | 1
    b[13] = HSWING[hswing]
    b[19] = sum(b[:19]) & 255
    return bytes(b)


def frame2(power, mode, temp, fan):
    b = bytearray([0x11, 0xDA, 0x27, 0x00, 0x00, 0, 0, 0, 0, 0, 0, 0x06, 0x60, 0x00, 0x02, 0xC7, 0x20, 0x24, 0])
    b[5] = MODES[mode] + 9 if power else MODES[mode] + 8
    b[6] = int(round(temp * 2))
    b[8] = (FANS[fan] << 4) | 0
    b[18] = sum(b[:18]) & 255
    return bytes(b)


def frame_pulses(data):
    p = [HDR_M, HDR_S]
    for byte in data:
        for i in range(8):
            p += [MARK, ONE if (byte >> i) & 1 else ZERO]
    p.append(MARK)
    return p


def pulses(f1, f2):
    return PRE + frame_pulses(f1) + [GAP] + frame_pulses(f2)


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

def encode(f1, f2):
    p = pulses(f1, f2)
    return base64.b64encode(compress(struct.pack("<%dH" % len(p), *p))).decode()


def decode_frames(code):
    r = decompress(base64.b64decode(code)); p = list(struct.unpack("<%dH" % (len(r) // 2), r))
    p = p[2:]  # preamble
    idx = [i for i, x in enumerate(p) if x > 20000]
    parts = []; s = 0
    for i in idx + [len(p)]:
        parts.append(p[s:i]); s = i + 1
    out = []
    for f in parts:
        body = f[2:]
        bits = "".join("1" if body[k + 1] > 900 else "0" for k in range(0, len(body) - 1, 2))
        out.append(bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits) - 7, 8)))
    return out


def temps(tmin, tmax):
    t = tmin
    while t <= tmax + 1e-9:
        yield t
        t += 0.5


def tkey(t):
    return str(int(t)) if t == int(t) else str(t)


def build(tmin=19, tmax=30):
    cmds = {}
    for mode in MODES:
        cmds[mode] = {}
        for fan in FANS:
            cmds[mode][fan] = {}
            for vs in VSWING:
                cmds[mode][fan][vs] = {}
                for hs in HSWING:
                    cmds[mode][fan][vs][hs] = {
                        tkey(t): encode(frame1(True, mode, vs, hs), frame2(True, mode, t, fan))
                        for t in temps(tmin, tmax)}
    for mode in MODES:
        cmds["off_" + mode] = encode(frame1(False, mode, "swing", "swing"), frame2(False, mode, 25, "auto"))
    return {
        "manufacturer": "Daikin",
        "supportedModels": ["ARC472A142"],
        "supportedController": "MQTT",
        "commandsEncoding": "Raw",
        "minTemperature": tmin,
        "maxTemperature": tmax,
        "precision": 0.5,
        "temperatureUnit": "C",
        "operationModes": ["cool", "heat"],
        "fanModes": list(FANS),
        "swingModes": list(VSWING),
        "swingHorizontalModes": list(HSWING),
        "commands": cmds,
    }


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "8480.json"
    d = build()
    json.dump(d, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
    print("wrote", out)
