#!/usr/bin/env python3
"""Generate SmartIR device JSON (Tuya/ZS06 IR codes) for the Daikin ARC476A2 remote.

Protocol (verified against real captures from the remote, see captures.json):
  two frames; frame 1 (20 bytes) is constant, frame 2 (19 bytes) carries the state.
  frame 2 byte 5 = 0x08 | power | mode<<4   (heat=4, cool=3)
  frame 2 byte 6 = temperature * 2
  frame 2 byte 8 = fan<<4 | flap1 swing (0xF swing / 0x0 still)   fan: auto=0xA quiet=0xB 1..5=3..7
  frame 2 byte 9 = flap2 swing (0xF / 0x0)
  frame 2 byte 18 = sum of bytes 0..17 (mod 256)
"""
import base64, json, struct, sys

FRAME1 = bytes([0x11, 0xDA, 0x27, 0x00, 0x01] + [0] * 14 + [0x13])
assert len(FRAME1) == 20 and FRAME1[-1] == sum(FRAME1[:-1]) & 255
MODES = {"heat": 4, "cool": 3}
FANS = {"auto": 0xA, "quiet": 0xB, "1": 3, "2": 4, "3": 5, "4": 6, "5": 7}
SWINGS = {"swing": 0xF, "still": 0x0}

# timings (us) measured from the real remote
MARK, ZERO, ONE = 394, 476, 1342
HDR_M, HDR_S = 3426, 1775
PRE = [394, 476, 390, 477, 392, 474, 424, 440, 395, 476, 391]  # 5 zero bits + mark
GAP1, GAP2 = 25196, 35791  # before frame 1 / between frames


def frame2(power, mode, temp, fan, swing):
    b = bytearray(19)
    b[0:4] = bytes([0x11, 0xDA, 0x27, 0x00])
    b[5] = 0x08 | (1 if power else 0) | (MODES[mode] << 4)
    b[6] = temp * 2
    b[8] = (FANS[fan] << 4) | SWINGS[swing]
    b[9] = SWINGS[swing]
    b[11:18] = bytes([0x06, 0x60, 0x00, 0x00, 0xC0, 0x00, 0x00])
    b[18] = sum(b[:18]) & 255
    return bytes(b)


def frame_pulses(data):
    p = [HDR_M, HDR_S]
    for byte in data:
        for i in range(8):
            p += [MARK, ONE if (byte >> i) & 1 else ZERO]
    p.append(MARK)  # stop mark
    return p


def pulses(f2):
    return PRE + [GAP1] + frame_pulses(FRAME1) + [GAP2] + frame_pulses(f2)


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


def decode_frame2(code):
    r = decompress(base64.b64decode(code)); p = list(struct.unpack("<%dH" % (len(r) // 2), r))
    idx = [i for i, x in enumerate(p) if x > 20000]
    f = p[idx[1] + 1:]
    body = f[2:]
    bits = [1 if body[k + 1] > 900 else 0 for k in range(0, len(body) - 1, 2)]
    s = "".join(map(str, bits))
    return bytes(int(s[i:i + 8][::-1], 2) for i in range(0, len(s) - 7, 8))


def build(tmin=14, tmax=30):
    cmds = {}
    for mode in MODES:
        cmds[mode] = {}
        for fan in FANS:
            cmds[mode][fan] = {}
            for sw in SWINGS:
                cmds[mode][fan][sw] = {str(t): encode(frame2(True, mode, t, fan, sw)) for t in range(tmin, tmax + 1)}
    cmds["off_heat"] = encode(frame2(False, "heat", 22, "auto", "still"))
    cmds["off_cool"] = encode(frame2(False, "cool", 26, "auto", "still"))
    return {
        "manufacturer": "Daikin",
        "supportedModels": ["ARC476A2"],
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
    out = sys.argv[1] if len(sys.argv) > 1 else "8476.json"
    d = build()
    json.dump(d, open(out, "w"), ensure_ascii=False, indent=2)
    print("wrote", out)
