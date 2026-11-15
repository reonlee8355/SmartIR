#!/usr/bin/env python3
"""Check gen.py against the real captures (captures.json) and the generated JSON round-trip.
frame1[5] (counter-like byte) and the frame1 checksum are compared after normalising the counter."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import gen

inv = lambda d: {v: k for k, v in d.items()}
caps = json.load(open(os.path.join(os.path.dirname(__file__), "captures.json")))["captures"]
bad = 0
for c in caps:
    f1, f2 = bytes.fromhex(c["frame1"]), bytes.fromhex(c["frame2"])
    power = f2[5] & 1 == 1
    mode = "cool" if (f2[5] >> 4) == 3 else "heat"
    temp = f2[6] / 2
    fan = inv(gen.FANS).get(f2[8] >> 4)
    vs = inv(gen.VSWING).get(f1[12] >> 4)
    hs = inv(gen.HSWING).get(f1[13])
    if fan is None or vs is None or hs is None:
        # fan 2-4 / unusual values were not captured; report only
        print("??", c["capture"], fan, vs, hs); bad += 1; continue
    g1 = bytearray(gen.frame1(power, mode, vs, hs)); g1[5] = f1[5]; g1[19] = sum(g1[:19]) & 255
    ok = bytes(g1) == f1 and gen.frame2(power, mode, temp, fan) == f2
    bad += not ok
    print("OK " if ok else "NG ", c["capture"], mode, "on" if power else "off", temp, fan, vs, hs)
d = gen.build()
n = 0
for mode, fans in d["commands"].items():
    if not isinstance(fans, dict): continue
    for fan, vss in fans.items():
        for vs, hss in vss.items():
            for hs, ts in hss.items():
                for t, code in ts.items():
                    f1, f2 = gen.decode_frames(code)
                    assert f1 == gen.frame1(True, mode, vs, hs) and f2 == gen.frame2(True, mode, float(t), fan)
                    n += 1
for k in ("off_heat", "off_cool"):
    f1, f2 = gen.decode_frames(d["commands"][k]); assert f2[5] & 1 == 0 and f1[6] == 0xC4
print("round-trip ok for", n, "codes + 2 off codes; capture mismatches:", bad)
sys.exit(1 if bad else 0)
