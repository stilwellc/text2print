#!/bin/bash
cd /Users/collin/Dev/text2print; C=slice_out/prusa; P=/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer
.venv/bin/python printcheck.py face > face_check.txt 2>/dev/null &
"$P" --export-gcode --load $C/centauri_04_016.ini --output $C/face.gcode sofubi_ape_face.stl > $C/face.log 2>&1
wait; echo FACEDONE >> face_check.txt
