#!/bin/bash
# egg-head ape (Sep 25): marks the base, then islands + exterior overhangs + PrusaSlicer at 0.2 mm, bare and with organic tree supports
cd /Users/collin/Dev/text2print; C=slice_out/prusa; P=/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer
.venv/bin/python kaiju_mark.py > slice_out/mark.log 2>&1
.venv/bin/python kaiju_eye.py > slice_out/eye.log 2>&1
.venv/bin/python printcheck.py base face cap ear_left ear_right horn_left horn_right > all_check.txt 2>&1 &
.venv/bin/python overhangs.py base face cap ear_left ear_right horn_left horn_right > overhang_check.txt 2>&1 &
for p in base face cap ear_left ear_right horn_left horn_right eye fang_upper fang_lower pin pin_tooth; do
  "$P" --export-gcode --load $C/centauri_04_020.ini --output $C/${p}_020.gcode sofubi_ape_$p.stl > $C/${p}_020.log 2>&1
  "$P" --export-gcode --load $C/centauri_04_020_tree.ini --output $C/${p}_020_tree.gcode sofubi_ape_$p.stl > $C/${p}_020_tree.log 2>&1
done
wait; echo FINALDONE >> all_check.txt
for p in face cap; do for t in 55 60; do "$P" --export-gcode --load $C/centauri_04_020_tree$t.ini --output $C/${p}_020_tree$t.gcode sofubi_ape_$p.stl > $C/${p}_020_tree$t.log 2>&1; done; done
echo SUPDONE >> all_check.txt
