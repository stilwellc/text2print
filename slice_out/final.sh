#!/bin/bash
cd /Users/collin/Dev/text2print; C=slice_out/prusa; P=/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer
.venv/bin/python printcheck.py ear_left ear_right base cap face > all_check.txt 2>/dev/null &
for p in base face cap ear_left ear_right; do "$P" --export-gcode --load $C/centauri_04_016.ini --output $C/$p.gcode sofubi_ape_$p.stl > $C/$p.log 2>&1; done
"$P" --export-gcode --load $C/bp_support.ini --output $C/cap_sup.gcode sofubi_ape_cap.stl > $C/cap_sup.log 2>&1
wait; echo FINALDONE >> all_check.txt
