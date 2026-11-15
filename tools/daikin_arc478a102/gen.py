#!/usr/bin/env python3
"""Generate SmartIR device JSON (Tuya/ZS06 IR codes) for the Daikin ARC478A102 remote (事務所).

Protocol (decoded from real captures of the remote, see captures.json; two frames of 20 and 19 bytes,
same family as the ARC476A2/ARC472A142). Byte indexes are 0-based.
  frame 1 (20 bytes): 11 da 27 00 02 00 00 00 00 [9] 00 [11] [12] 00 50 00 00 00 00 [19]
     [9]   mode: cool 0x0e, heat 0x10, off 0x02
     [11]  0x00 on, 0x80 off
     [12]  vertical swing: auto=0x01, position n = n<<4 | 1  (1,3,5 captured; 2,4 interpolated)
     [19]  sum of bytes 0..18 (mod 256)
  frame 2 (19 bytes): 11 da 27 00 00 [5] [6] 00 [8] 00 00 06 60 00 00 c3 00 00 [18]
     [5]   mode<<4 | 8 | power: cool on 0x39, heat on 0x49, cool off 0x38, heat off 0x48
     [6]   temperature * 2
     [8]   fan<<4 | swing nibble (auto swing 0xf, fixed position 0): fan auto=0xa quiet=0xb 1=3 3=5 5=7 (2,4 interpolated)
     [18]  sum of bytes 0..17 (mod 256)
Timings: means of the 14 real captures (11 preamble pulses + gap + frame 1 + gap + frame 2).
"""
import base64, json, struct, sys

MODES = {"cool": 0x30, "heat": 0x40}
F1_MODE = {"cool": 0x0E, "heat": 0x10}
FANS = {"auto": 0xA, "quiet": 0xB, "1": 3, "2": 4, "3": 5, "4": 6, "5": 7}
SWINGS = ["auto", "1", "2", "3", "4", "5"]

PRE = [438, 427, 443, 419, 442, 429, 438, 427, 438, 415, 443]
GAP1, GAP2 = 25104, 35160
HDR_M, HDR_S = 3529, 1718
MARK, ZERO, ONE = 446, 426, 1311


def frame1(power, mode, swing):
    b = bytearray([0x11, 0xDA, 0x27, 0x00, 0x02, 0, 0, 0, 0, 0, 0, 0, 0x01, 0, 0x50, 0, 0, 0, 0, 0])
    if power:
        b[9] = F1_MODE[mode]
    else:
        b[9], b[11] = 0x02, 0x80
    b[12] = 0x01 if swing == "auto" else (int(swing) << 4) | 1
    b[19] = sum(b[:19]) & 255
    return bytes(b)


def frame2(power, mode, temp, fan, swing):
    b = bytearray([0x11, 0xDA, 0x27, 0x00, 0x00, 0, 0, 0, 0, 0, 0, 0x06, 0x60, 0, 0, 0xC3, 0, 0, 0])
    b[5] = MODES[mode] + (9 if power else 8)
    b[6] = int(round(temp * 2))
    b[8] = (FANS[fan] << 4) | (0xF if swing == "auto" else 0)
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
    return PRE + [GAP1] + frame_pulses(f1) + [GAP2] + frame_pulses(f2)


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
    p = p[len(PRE) + 1:]
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


def build(tmin=18, tmax=30):
    cmds = {}
    for mode in MODES:
        cmds[mode] = {fan: {sw: {str(t): encode(frame1(True, mode, sw), frame2(True, mode, t, fan, sw))
                                 for t in range(tmin, tmax + 1)} for sw in SWINGS} for fan in FANS}
        cmds["off_" + mode] = encode(frame1(False, mode, "auto"), frame2(False, mode, 25, "auto", "auto"))
    return {
        "manufacturer": "Daikin",
        "supportedModels": ["ARC478A102"],
        "supportedController": "MQTT",
        "commandsEncoding": "Raw",
        "minTemperature": tmin,
        "maxTemperature": tmax,
        "precision": 1,
        "temperatureUnit": "C",
        "operationModes": ["cool", "heat"],
        "fanModes": list(FANS),
        "swingModes": SWINGS,
        "commands": cmds,
    }


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "8481.json"
    json.dump(build(), open(out, "w"), ensure_ascii=False, indent=2)
    print("wrote", out)
