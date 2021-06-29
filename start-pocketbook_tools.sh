#! /bin/sh
exportdir=/ramdisk/
logdir=/ramdisk/
zip=pocketbook_tools.zip
cd ~/workbench/calibre-pocketbook-tools/
#rm $exportdir/$zip"
zip -ur $exportdir/$zip *.py *.txt icon.png help/ images/ && echo "- $zip created"
case "$1" in
        zip) exit 0 ;;
	ZIP) exit 0 ;;
        *) echo "- Starting calibre" ;;
esac
calibre-customize -a $exportdir/$zip
calibre-debug  -s
calibre-debug  -g > $logdir/pocketbook_tools-log.txt
