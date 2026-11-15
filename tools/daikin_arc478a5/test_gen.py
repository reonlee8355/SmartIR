#!/usr/bin/env python3
"""Check gen.py against the real captures (captures.json) and the generated JSON round-trip."""
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
    fan = inv(gen.FANS)[f2[8] >> 4]
    sw = "auto" if f2[8] & 15 == 0xF else str(f1[12] >> 4)
    ok = gen.frame1(power, mode, sw) == f1 and gen.frame2(power, mode, temp, fan, sw) == f2
    bad += not ok
    print("OK " if ok else "NG ", c["capture"], mode, "on" if power else "off", temp, fan, sw)
d = gen.build(); n = 0
for mode, fans in d["commands"].items():
    if not isinstance(fans, dict): continue
    for fan, sws in fans.items():
        for sw, ts in sws.items():
            for t, code in ts.items():
                f1, f2 = gen.decode_frames(code)
                assert f1 == gen.frame1(True, mode, sw) and f2 == gen.frame2(True, mode, int(t), fan, sw)
                n += 1
for k in ("off_heat", "off_cool"):
    f1, f2 = gen.decode_frames(d["commands"][k]); assert f2[5] & 1 == 0 and f1[11] == 0x80
print("round-trip ok for", n, "codes + 2 off codes; capture mismatches:", bad)
sys.exit(1 if bad else 0)
