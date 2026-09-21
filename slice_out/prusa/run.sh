#!/bin/bash
cd /Users/collin/Dev/text2print
P="/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer"
CFG="$PWD/slice_out/prusa/centauri_04_016.ini"
for part in pin base neck cap face; do
  f="sofubi_ape_$part.stl"
  "$P" --export-gcode --load "$CFG" --output "slice_out/prusa/$part.gcode" "$f" > "slice_out/prusa/$part.log" 2>&1
  echo "$part exit $?" >> slice_out/prusa/progress.txt
done
echo ALLDONE >> slice_out/prusa/progress.txt
