#!/bin/sh
# Build the CPC Nokia MIDlet inside the j2me toolchain container.
# Mounted at /work; tools at /tools (from vipaoL/j2me-build-tools).
set -e
T=/tools
CP="$T/lib/midp21.jar:$T/lib/cldc11.jar:$T/lib/jsr135.jar:$T/lib/jsr82.jar:$T/lib/jsr75_file.jar:$T/lib/nokiaui.jar"

rm -rf classes preverified stage RobotMIDlet.jar RobotMIDlet.jad
mkdir -p classes preverified stage

echo "=== compile ==="
javac -bootclasspath "$CP" -source 1.3 -target 1.3 -d classes src/*.java

echo "=== preverify ==="
# preverify resolves class NAMES against -classpath (not a dir arg), so add the
# compiled classes dir to the path and pass every class by name. Inner-class names
# carry '$', which the shell would expand -> feed the list via preverify's @file.
( cd classes && find . -name '*.class' | sed 's|^\./||;s|\.class$||;s|/|.|g' | tr '\n' ' ' ) > classlist.txt
"$T/bin/preverify" -classpath "$CP:classes" -d preverified @classlist.txt
echo "--- preverified/ ---"; ls -R preverified

echo "=== assemble jar ==="
cp -r preverified/. stage/
( cd stage && jar cfm ../CpcPad.jar ../MANIFEST.MF . )

SIZE=$(stat -c%s CpcPad.jar)
grep -v '^Manifest-Version' MANIFEST.MF > CpcPad.jad
echo "MIDlet-Jar-URL: CpcPad.jar" >> CpcPad.jad
echo "MIDlet-Jar-Size: $SIZE" >> CpcPad.jad

echo "=== BUILT ==="
ls -l CpcPad.jar CpcPad.jad
echo "--- jar contents ---"
jar tf CpcPad.jar
