#!/usr/bin/env python3
"""Check gen.py against the real captures (captures.json) and the generated JSON round-trip."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import gen

caps = json.load(open(os.path.join(os.path.dirname(__file__), "captures.json")))["captures"]
bad = 0
for c in caps:
    exp1, exp2 = bytes.fromhex(c["frame1"]), bytes.fromhex(c["frame2"])
    got2 = gen.frame2(c["power"], c["mode"], c["temp"], c["fan"], c["swing"])
    ok = exp1 == gen.FRAME1 and exp2 == got2
    bad += not ok
    print("OK " if ok else "NG ", c["capture"], "" if ok else got2.hex(" "))
d = gen.build()
n = 0
for mode, fans in d["commands"].items():
    if not isinstance(fans, dict): continue
    for fan, sws in fans.items():
        for sw, temps in sws.items():
            for t, code in temps.items():
                f1, f2 = gen.decode_frames(code)
                assert f1 == gen.FRAME1 and f2 == gen.frame2(True, mode, int(t), fan, sw), (mode, fan, sw, t)
                assert f2[18] == sum(f2[:18]) & 255
                n += 1
for k in ("off_heat", "off_cool"):
    f1, f2 = gen.decode_frames(d["commands"][k]); assert f2[5] & 1 == 0
print("round-trip ok for", n, "codes + 2 off codes; capture mismatches:", bad)
sys.exit(1 if bad else 0)
