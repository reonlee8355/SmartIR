#!/usr/bin/env python3
"""Generate SmartIR device JSON (Tuya/ZS06 IR codes) for the Panasonic A75C3190 remote
(air conditioner in the 配膳室).

Protocol (decoded from real captures of the remote, see captures.json; 27 bytes in two frames,
the same layout as IRremoteESP8266's Panasonic AC: header ~3.58ms/1.68ms, gap ~10ms between frames).
Byte indexes are 0-based.
  frame 1 (8 bytes)  : 02 20 e0 04 00 00 00 06                      (constant)
  frame 2 (19 bytes) :
     [0:5]  02 20 e0 04 00   constant
     [5]    mode<<4 | power      cool=3 heat=4, power 1=on 0=off
     [6]    temperature * 2      (16..30C)
     [7]    80                   constant
     [8]    fan<<4 | swing       fan: auto=0xa, quiet and fan 1 = 3, fan 2 = 4, fan 3 = 5, fan 4 = 7
                                 (6 is not used by this remote); swing: auto=0xf, positions 1..5 = 1..5
     [9]    00, [10] 00, [11] 06, [12] 60   constant
     [13]   flags: quiet = 0x20, powerful = 0x01 (powerful keeps the fan nibble at auto)
     [14]   00, [15] 80, [16] 00   constant
     [17]   06, or 16 only when cool + fan auto + no quiet/powerful flag (observed on cool; heat/auto = 06)
     [18]   sum of bytes 0..17 (mod 256)
Notes:
  * swing positions 2..4 were not captured (assumed 2, 3, 4); 1, 5 and auto were captured.
  * The remote cannot start the unit in powerful mode from OFF; the generated "on + powerful" code
    is the same signal the remote sends when powerful is pressed while running.
  * OFF keeps the rest of the state of the last mode (power bit cleared), like the Daikin remotes.
"""
import base64, json, struct, sys

FRAME1 = bytes([0x02, 0x20, 0xE0, 0x04, 0x00, 0x00, 0x00, 0x06])
MODES = {"heat": 4, "cool": 3}
FANS = {"auto": 0xA, "quiet": 3, "1": 3, "2": 4, "3": 5, "4": 7, "powerful": 0xA}
SWINGS = {"auto": 0xF, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5}

# timings (us): means of the real captures (15 captures, 30 frames)
HDR_M, HDR_S = 3575, 1685
MARK, ZERO, ONE = 471, 413, 1285
GAP = 9991


def frame2(power, mode, temp, fan, swing):
    b = bytearray(19)
    b[0:5] = bytes([0x02, 0x20, 0xE0, 0x04, 0x00])
    b[5] = (MODES[mode] << 4) | (1 if power else 0)
    b[6] = temp * 2
    b[7] = 0x80
    b[8] = (FANS[fan] << 4) | SWINGS[swing]
    b[11] = 0x06
    b[12] = 0x60
    flag = {"quiet": 0x20, "powerful": 0x01}.get(fan, 0)
    b[13] = flag
    b[15] = 0x80
    b[17] = 0x16 if (mode == "cool" and fan == "auto") else 0x06
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
    """Return [frame1_bytes, frame2_bytes] from a Tuya code (header 3000-4000us, gap ~10ms, space>900us = 1)."""
    r = decompress(base64.b64decode(code)); p = list(struct.unpack("<%dH" % (len(r) // 2), r))
    parts = []; cur = []
    for x in p:
        cur.append(x)
        if x > 5000 and len(cur) > 10: parts.append(cur[:-1]); cur = []
    if cur: parts.append(cur)
    out = []
    for f in parts:
        assert 3000 < f[0] < 4000
        body = f[2:]
        bits = "".join("1" if body[k + 1] > 900 else "0" for k in range(0, len(body) - 1, 2))
        out.append(bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits) - 7, 8)))
    return out


def build(tmin=16, tmax=30):
    cmds = {}
    for mode in MODES:
        cmds[mode] = {}
        for fan in FANS:
            cmds[mode][fan] = {}
            for sw in SWINGS:
                cmds[mode][fan][sw] = {str(t): encode(frame2(True, mode, t, fan, sw)) for t in range(tmin, tmax + 1)}
    cmds["off_heat"] = encode(frame2(False, "heat", 25, "auto", "auto"))
    cmds["off_cool"] = encode(frame2(False, "cool", 25, "auto", "auto"))
    return {
        "manufacturer": "Panasonic",
        "supportedModels": ["A75C3190"],
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
    out = sys.argv[1] if len(sys.argv) > 1 else "8479.json"
    d = build()
    json.dump(d, open(out, "w"), ensure_ascii=False, indent=2)
    print("wrote", out)
