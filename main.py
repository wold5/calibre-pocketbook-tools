import os, shutil, filecmp, sqlite3, json, zipfile
import time, datetime
import logging
logger = logging.getLogger('pbt_logger.main')


def getexplorerdb(root):
    """Returns location of explorer-x.db, where x is 3 or 2."""
    for version in (3, 2):
        explorer = 'explorer-%i' % version
        dbpath = os.path.join(root, 'system', explorer, explorer + '.db')
        logger.debug(dbpath)
        if os.path.exists(dbpath):
            return dbpath
    return None


def sqlite_execute_query(db, query):
    """Returns results for a (simple) sqlite query to provided db path."""
    out = []
    con = sqlite3.connect(db)
    cursor = con.cursor()
    for row in cursor.execute(query):
        out += row
    con.close()
    logger.debug('%s' % out)
    return out or []


def profilepath(root, profile):
    """Returns a profile name's config path"""
    return os.path.join(root, 'system', 'profiles', profile, 'config')


def getprofilepaths(profilenames, mainpath, cardpath=None):
    """ Returns existing profile paths. Depends on correctness of explorerdb profiles."""
    profilepaths = [('defaultroot', os.path.join(mainpath, 'system', 'config'))]  # stock
    for profile in profilenames:
        if not profile.startswith('/'):
            # for root in (mainpath, cardpath):
            #    profilepaths += profilepath(root, profile)
            profilepaths += [(profile, profilepath(root, profile)) for root in (mainpath, cardpath) if root]
    profilepaths = [(profile, profpath) for (profile, profpath) in profilepaths if os.path.exists(profpath)]
    return profilepaths


def _checkfile(srcpath=None):
    """Basic checks consisting of file existing and size > 0."""
    if srcpath and os.path.exists(srcpath):
        if os.stat(srcpath).st_size > 0:
            return True
    return False


def _pb_filedest(ext):
    """Simple file extension identifier, returns filetype label and (relative) destination directory on device."""
    FORMAT_EXTENSIONS = {
        '.ttf': ('FONT', 'system/fonts/'),
        '.otf': ('FONT', 'system/fonts/'),
        '.dic': ('DICT', 'system/dictionaries/'),
        '.pbi': ('INSTALLER', ''),
        '.app': ('APP', 'applications/'),
        '.acsm': ('ACSM', ''),
    }
    return FORMAT_EXTENSIONS.get(ext, (None, None))


class PbFileref:
    """WIP file object class. Contains source, destination and filetype details."""
    def __init__(self, path, zipinfo):
        if not zipinfo:
            self.srcpath = path
            self.zipinfo = self.zipparent = None
        else:
            self.zipparent = path
            self.zipinfo = zipinfo
            self.srcpath = zipinfo.filename

        self.path, self.filename = os.path.split(self.srcpath)
        self.filetype, self.dest_rel = _pb_filedest(os.path.splitext(self.filename)[1])
        # self.dest_full = None
        self.dest_root = None
        self.dest_filename = self.filename

    def __setattr__(self, name, value):
        if name == 'dest_filename':
            self.__dict__['dest_filename'] = value
            self._setdest()
        self.__dict__[name] = value

    def setroot(self, dest_root):
        self.dest_root = dest_root
        self.process = None
        self.msg = None
        self._setdest()

    def _setdest(self):
        if self.dest_root is not None and self.dest_rel is not None:
            self.dest_full = os.path.join(self.dest_root, self.dest_rel, self.dest_filename)
        else:
            self.dest_full = None

    def setstate(self, process, msg):
        self.process = process
        self.msg = msg

    def __call__(self):
        return self.srcpath, self.dest_full

    def __repr__(self):
        return '%s (%s)' % (self.filename, self.filetype or 'UNKNOWN')

    def __str__(self):
        return '%s to %s' % (self.srcpath, self.dest_full)


def copyfile(srcpath, destpath):
    """Copy file using shutil.copy. Returns True on success."""
    try:
        shutil.copy(srcpath, destpath)
    except:  # 'OSERROR':
        logger.exception('Copy failed: %s - %s' % (srcpath, destpath))
        return False
    else:
        if filecmp.cmp(srcpath, destpath, shallow=False):
            return True
        else:
            return False


def copymovefile(srcpath, destpath):
    """Wrapper for copyfile. Performs copies using an interim *.tmp file."""
    dest_tmp = destpath + '.tmp'
    result = copyfile(srcpath, dest_tmp)
    if not result:
        return False

    try:
        shutil.move(dest_tmp, destpath)
    except:
        logger.exception('Move failed: %s - %s' % (dest_tmp, destpath))
        return False
    else:
        if filecmp.cmp(srcpath, destpath, shallow=False):
            return True
        else:
            return False


def copyzipfile(zipparent, zipinfo, destpath):
    """Extracts a zipfile's bytes directly to a file, forgoing extraction.
    Loses metadata. Mind ram usage with large files (alt: loop block copy in py3.x)"""

    with zipfile.ZipFile(zipparent, 'r') as zipf:
        filecontent = zipf.read(zipinfo)

    if filecontent:
        try:
            with open(destpath, 'wb') as fout:
                fout.write(filecontent)
        except:
            logger.exception('Zip extract failed: %s - %s' % (zipinfo, destpath))
        else:
            # fix mod/access time for linux/mac
            datetime_epoch = time.mktime(zipinfo.date_time + (0, 0, -1))
            os.utime(destpath, times=(datetime_epoch, datetime_epoch))
            return True

    return


def dbbackup(profile, bookdbpath, exportdir, labeltime=True):
    """Copies db files labeled with profile and datetime."""
    logger.debug('start dbbackup')
    dbname = os.path.basename(bookdbpath)
    time = '-' + datetime.datetime.now().strftime("%Y-%b-%d_%H-%M") if labeltime else '' # avoid colons on windows (streams)
    dest = os.path.join(exportdir, dbname + '-' + profile + time + '.db')
    return copyfile(bookdbpath, dest)


def fileuploader(files, mainpath, cardpath=None, zipenabled=False, replace=False, deletemode=0, gui=False):
    """Copy supported files to device main or card memory. See pbfile class for supported files."""
    fileobjs = []
    for filepath in files:
        fileobjs.extend(_uploader_getfileobj(filepath, zipenabled=zipenabled))

    logger.debug('File objects: %s' % fileobjs)

    for f in fileobjs:
        _uploader_setdest(f, mainpath, cardpath=cardpath, replace=replace, gui=gui)

    # do future GUI interaction here
    filestodelete = set()
    for fileobj in fileobjs:
        if fileobj.process:
            if not fileobj.zipparent:
                copied = copymovefile(*fileobj())
            else:
                copied = copyzipfile(fileobj.zipparent, fileobj.zipinfo, fileobj.dest_full)

            if not copied:
                fileobj.setstate(False, 'Copying or extraction failed')
            elif not fileobj.msg:
                if (deletemode >= 1 and not fileobj.zipparent and fileobj.filetype == 'ACSM') or\
                        (deletemode >= 2 and fileobj.zipparent) or deletemode == 3:
                    logger.debug(
                        'Deleting - deletemode %d, filetype %s, srcpath: %s, zipparent: %s'
                        % (deletemode, fileobj.filetype, fileobj.filename, fileobj.zipparent))
                    if fileobj.zipparent:
                        logger.debug('Deleting zipfile %s' % fileobj.zipparent)
                        filestodelete.add(fileobj.zipparent)
                    else:
                        filestodelete.add(fileobj.srcpath)
                    fileobj.setstate(True, 'Copied or extracted file (deleted source)')
                else:
                    fileobj.setstate(True, 'Copied or extracted file')

    logger.debug('filestodelete: %s' % filestodelete)
    for each in filestodelete:
        os.remove(each)

    # [logger.debug('CHECK %s %s' % (x.filename, x.msg)) for x in fileobjs]
    text = '\n'.join([': '.join((x.filename.ljust(40), x.msg)) for x in fileobjs])  #

    return text


def _cli_prompt_filename(dest, filename):
    """CLI user-interaction regarding existing files"""
    def _compare_file_ext(a, b):
        return os.path.splitext(a)[1] == os.path.splitext(b)[1]

    while True:
        reply = input('Filename %s exists: (R)eplace, Re(N)ame, (S)kip: ' % filename)
        reply = reply.lower()
        if reply in ('r', 'n', 's'):
            break

    if reply == 's':
        return
    elif reply == 'r':
        return filename
    elif reply == 'n':
        destparent = os.path.dirname(dest)
        while True:
            reply = input('? Provide new filename with same extension for \'%s\': ' % filename)
            dest = os.path.join(destparent, reply)
            if reply != filename and _compare_file_ext(reply, filename):
                print('! Copying %s as %s' % (filename, dest))
                return reply
            elif reply != '' and os.path.exists(dest):
                print('! New filename already exists!')
            # else:
            #    print('! Different filename and/or different extension required')


def _uploader_getfileobj(filepath, zipenabled=False):
    """Creates fileobj from filepath or zipfile contents (multiple files). Returns list."""
    import zipfile
    fileobjs = []
    if not zipfile.is_zipfile(filepath):
        fileobj = PbFileref(filepath, None)
        if not _checkfile(fileobj.srcpath):
            fileobj.setstate(False, "Skipped, checkfile failed")
        else:
            fileobjs.append(fileobj)
    elif zipenabled:
        with zipfile.ZipFile(filepath, 'r') as zf:
            zipfiles = [(filepath, zipfile) for zipfile in zf.infolist() if not zipfile.is_dir()]
            for zipfile in zipfiles:
                fileobjs.append(PbFileref(*zipfile))
        zf.close()
    return fileobjs


def _uploader_setdest(file, mainpath, cardpath=None, replace=False, gui=False):
    """Set fileobj destination folder and/or root, and check existence."""
    if cardpath and file.filetype == 'ACSM':
        file.setroot(cardpath)
        logger.debug('Copying %s to card' % file.filename)
    elif file.filetype:
        file.setroot(mainpath)
    elif not file.filetype:
        file.setstate(False, 'Skipped, unknown file extension')
        return file

    if os.path.exists(file.dest_full):
        if not file.zipparent and filecmp.cmp(*file()):
            file.setstate(False, 'Skipped, identical file exists')
        else:
            if replace:
                file.setstate(True, None)  # 'Replacing existing file')
            elif not gui:
                filename = _cli_prompt_filename(file.dest_full, file.filename)
                if not filename:
                    file.setstate(False, 'Skipped, by user')
                else:
                    if filename == file.filename:
                        file.setstate(True, None)  # 'Replacing')
                    else:
                        file.dest_filename = filename
                        file.setstate(True, 'Copying using new name: %s' % filename)
            else:
                pass
                # cannot yet set gui replace (Y/N, change filename)
    else:
        file.setstate(True, None)  # Files to copy omit msg.

    logger.debug('%s: %s - %s' % (file.filename, file.process, file.msg))
    return file


def export_htmlhighlights(db, sortontitle=False, outputfile=None):
    """Queries a books.db and writes out highlight entries to a HTML file."""
    if not outputfile:
        return False

    con = sqlite3.connect(db)
    # con.row_factory = sqlite3.Row
    # cur = con.cursor()
    # query improves upon https://www.mobileread.com/forums/showpost.php?p=3740634&postcount=36
    query = '''
        SELECT Title, Authors, Val,
        CAST(substr(Val, instr(Val,'page=') + 5, (instr(Val,'&') - instr(Val,'page=') - 5)) AS INTEGER) AS Page,
        CAST(substr(Val, instr(Val,'offs=') + 5, (instr(Val,'#') - instr(Val,'offs=') - 5)) AS INTEGER) AS PageOffset
        from Books b
        LEFT JOIN (SELECT OID, ParentID from Items WHERE State = 0) i on i.ParentID = b.OID
        INNER JOIN (SELECT OID, ItemID, Val from Tags where TagID = 104 and Val <> '{"text":"Bookmark"}') t on t.ItemID = i.OID
        '''

    if sortontitle:
        query += '\nORDER BY Title, Authors, Page, PageOffset;'

    with open(outputfile, 'wt') as out:
        out.write('<HTML><head><style>td {vertical-align: top;}</style></head><BODY><TABLE>\n')
        out.write("<TR><TH>Title</TH>"
                  "<TH>Authors</TH>"
                  "<TH>Highlight</TH>"
                  "<TH>Page</TH>"
                  "</TR>\n")
        for title, authors, val, page, pageoffset in con.execute(query):
            valdict = json.loads(val)
            highlight = valdict.get('text', '').replace('\n', '<br />')  # circumvents missing json1 ext on Windows
            # notes app edited highlights lose page & offset
            if 'begin' in valdict:
                page += 1
            else:
                page = '?'
            htmlrow = "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td></tr>\n".format(title, authors or '-', highlight, page)
            out.write(htmlrow)
        out.write('</TABLE></BODY></HTML>')

    return True
    con.close()


def mergefix_annotations(dbpath):
    """Merge/fixes annotations for a given books.db, by modifying Parent_ID values of Item table rows."""
    query_dupes = '''
                SELECT * FROM(
                    SELECT Title, Authors,
                    COUNT(*) OVER (PARTITION BY Title, Authors) AS COUNTS,
                    OID,
                    MAX(OID) OVER (PARTITION BY Title, Authors) AS MAXOID
                    FROM Books ORDER BY Title, Authors, OID DESC
                ) WHERE COUNTS > 1
                    '''

    query_update = "UPDATE Items SET ParentID = ? WHERE ParentID = ?"

    # Given the early release, we do a backup just to be sure
    copied = copyfile(dbpath, dbpath + '.backup')
    logger.debug('Early release DB backup %s' % copied)

    db = dbpath
    con = sqlite3.connect(db)
    cursorupdate = con.cursor()

    report = ''
    reportline = None
    for title, authors, count, oid, maxoid in con.execute(query_dupes):
        if count == 1:
            reportline = None
        elif oid == maxoid:
            reportline = 'Checking title \'%s\' by \'%s\' (max oid: %s)' % (title, authors, maxoid)
        elif oid < maxoid:
            result = cursorupdate.execute(query_update, (maxoid, oid))
            if result.rowcount:
                reportline = '- Changed %d rows, setting Item\'s ParentID from %s to %s (for \'%s\')'\
                             % (result.rowcount, oid, maxoid, title)
            else:
                reportline = '- Nothing to change for oid %s (\'%s\')' % (oid, title)
        else:
            logger.debug("! Unknown issue for %s %s %s %s" % (title, authors, oid, maxoid))

        if reportline:
            report += reportline + '\n'
            logger.debug(reportline)

    con.commit()
    changedrows = con.total_changes
    reportline = '\nTotal rows changed: %s\n\n' % changedrows
    report += reportline
    logger.debug(reportline)

    con.close()

    return report, changedrows


if __name__ == "__main__":
    import argparse

    # CLI currently supports only fileuploader
    description = "Uploads .acsm or font/dict/pbi/app files to a mounted Pocketbook e-reader. " \
                  "If cardpath is provided, .acsm files are copied there."
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-v', '--debug', dest='debug', action='store_true', help='Print debug output')
    parser.add_argument('-z', '--zip', dest='zipenabled', action='store_true', help='Enable experimental zip support')
    parser.add_argument('-a', '--alwaysreplace', dest='replace', action='store_true', help='Enable support')
    parser.add_argument('-m', '--mainpath', required=True, help='Path to mounted Pocketbook e-reader root')
    parser.add_argument('-c', '--cardpath', required=False,
                        help='Optional path to a mounted SD card of a Pocketbook reader, for copying .acsm files')
    parser.add_argument('-i', '--files', dest='files', required=True, nargs='*',
                        help='One or more .acsm/.ttf/.otf/.app/.dict/.pbi files')
    args = parser.parse_args()

    if args.debug:
        import logging
        logger = logging.getLogger('pbt_logger')
        logger.setLevel(logging.DEBUG)
        console = logging.StreamHandler()
        console.setFormatter(
            logging.Formatter('%(relativeCreated)d %(levelname)s - %(filename)s:%(lineno)d:%(funcName)s - %(message)s'))
        logger.addHandler(console)

        logger.debug(args)
        for path in args.files:
            logger.debug('realpath: ' + os.path.realpath(path))

    # start
    if args.zipenabled:
        import zipfile

    text = fileuploader(files=args.files,
                        mainpath=args.mainpath,
                        cardpath=args.cardpath if args.cardpath else None,
                        zipenabled=args.zipenabled,
                        replace=args.replace,
                        gui=False)

    print(text)
