#! /bin/sh
testdir=/ramdisk/
./start-pocketbook_tools.sh ZIP
cp *.bat $testdir

case "$1" in
	3) continue ;;
	*) exit 0 ;;
esac

# create 3.x test environment with lux 2 driver
# run once
cd $testdir
git clone --reference ~/workbench/calibre https://github.com/wold5/calibre
cd /$testdir/calibre/
git checkout v3.48.0
cp ~/workbench/calibre/src/calibre/devices/misc.py ./src/calibre/devices/ && echo 'Copied pocketbook driver'
