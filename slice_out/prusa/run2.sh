#!/bin/bash
cd /Users/collin/Dev/text2print; P="/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer"; C=slice_out/prusa
"$P" --export-gcode --load $C/centauri_04_016.ini --output $C/face.gcode sofubi_ape_face.stl > $C/face.log 2>&1
"$P" --export-gcode --load $C/with_support.ini --output $C/face_sup.gcode sofubi_ape_face.stl > $C/face_sup.log 2>&1
for p in base neck cap; do "$P" --export-gcode --load $C/centauri_04_016.ini --output $C/$p.gcode sofubi_ape_$p.stl > $C/$p.log 2>&1; done
echo RUN2DONE >> $C/face.log
