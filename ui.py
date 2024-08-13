from calibre.constants import numeric_version as calibre_version
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.device import device_signals
from calibre.gui2 import info_dialog, error_dialog, question_dialog, open_url

try:
    from PyQt5.Qt import (Qt, QApplication, pyqtSignal, QIcon, QMenu, QAction, QRegularExpression, QUrl,
                          QColor, QHBoxLayout, QTableWidget, QTableWidgetItem)
except ImportError as e:
    print('Problem loading QT5: ', e)


try:
    from calibre.gui2 import choose_dir, choose_files, choose_save_file
except ImportError:
    # calibre <2.48.
    print('PBT will run, but is untested due to device driver issues. Consider using main.py CLI')
    from calibre.gui2.win_file_dialogs import choose_dir, choose_files, choose_save_file

from calibre.gui2.dialogs.message_box import MessageBox

import os, sqlite3, zipfile
from calibre_plugins.pocketbook_tools.config import prefs
from calibre.utils.config import config_dir
from calibre_plugins.pocketbook_tools.main import \
    getexplorerdb, sqlite_execute_query, profilepath, getprofilepaths, \
    uploader_prep, uploader_copy, export_htmlhighlights, dbbackup, \
    copyfile, mergefix_annotations
from calibre_plugins.pocketbook_tools.ui_dialogs import uploaderTW

# logging
import logging, logging.config

# logging.config.fileConfig(load_resources('logging.conf'))
logger = logging.getLogger('pbt_logger')
logger.setLevel(logging.DEBUG if prefs['debug'] else logging.INFO)
console = logging.StreamHandler()
console.setFormatter(
    logging.Formatter('%(asctime)s: %(levelname)s - %(filename)s:%(lineno)d:%(funcName)s - %(message)s'))  # %(relativeCreated)d
logger.addHandler(console)

PLUGIN_ICONS = ['images/icon.png']
URLMR = 'https://www.mobileread.com/forums/showthread.php?t=339806'

class PocketBookToolsPlugin(InterfaceAction):
    name = 'PocketBook Tools'

    # Declare the main action associated with this plugin
    # The keyboard shortcut can be None if you dont want to use a keyboard
    # shortcut. Remember that currently calibre has no central management for
    # keyboard shortcuts, so try to use an unusual/unused shortcut.
    action_spec = ('PocketBook Tools', None,
                   'PocketBook Tools', None)
    action_menu_clone_qaction = False
    action_add_menu = False
    popup_type = 2  # QToolButton.InstantPopup

    plugin_device_connection_changed = pyqtSignal(object)

    def genesis(self):
        # This method is called once per plugin, do initial setup here
        self.resources_path = os.path.join(config_dir, 'plugins', '')

        logger.debug('Starting v%d.%d.%d' % self.interface_action_base_plugin.version)
        logger.debug('prefs: %s' % prefs)

        self.connected_device = None
        self.mainpath = None
        self.cardpath = None
        self.explorerdbpath = None
        device_signals.device_connection_changed.connect(self.on_device_connection_changed)

        # add menu
        self.qaction.setIcon(get_icons(PLUGIN_ICONS[0]))
        self.menu = QMenu(self.gui)
        self.qaction.setMenu(self.menu)
        # self.menu.aboutToShow.connect(self.about_to_show_menu)
        self.menu_build()
        self.menu_toggle_deviceactions(present=False)

    def on_device_connection_changed(self, is_connected):
        # starts disconnected
        self.plugin_device_connection_changed.emit(is_connected)
        if is_connected:
            self.connected_device = self.gui.device_manager.device
            VID = getattr(self.connected_device, 'VENDOR_ID', 0)
            # For MacOS, the VID seems to stick to the first reported one, Google VID 0x18d1.
            # 0x1d6b is for the Color 3, and is also the Linux Foundation VID
            if VID in [[0xfffe], [0x18d1], [0x1d6b]]:
                logger.debug('Found PocketBook: %s' % self.connected_device)
                self.mainpath = getattr(self.connected_device, '_main_prefix', None)
                self.cardpath = self.connected_device.card_prefix()[0]

                self.explorerdbpath = getexplorerdb(self.mainpath)
                if not self.explorerdbpath:
                    logger.critical('Nothing found at explorerdb path. Blocking device functions.')
                    return
                self.profiles = sqlite_execute_query(self.explorerdbpath,
                                                     query="SELECT name from profiles")  # tested v37
                self.profilepaths = getprofilepaths(self.profiles, self.mainpath, self.cardpath)
                # alt: search for books.db. However, if count > 1 complexity becomes similar.
                self.bookdbs = [(profile, os.path.join(path, 'books.db')) for profile, path in self.profilepaths]

                self.menu_toggle_deviceactions(True)
                logger.debug('Explorerpath: %s' % self.explorerdbpath)
                logger.debug('Bookdb info: %s' % self.bookdbs)
        else:
            logger.debug('No PocketBook connected')
            self.menu_toggle_deviceactions(False)
            self.connected_device = None
            # Obsolete if menu is disabled, however, we may keep the menu pressed.
            self.mainpath = None
            self.cardpath = None
            self.explorerdbpath = None

    def menu_toggle_deviceactions(self, present=False):
        actions = self.menu.findChildren(QAction, QRegularExpression('pb_.*'))
        for action in actions:
            action.setEnabled(present)

        if present:
            self.deviceinfo.setText(_('Found PocketBook. Driver: %s' % self.connected_device.name or 'Unknown'))
        else:
            self.deviceinfo.setText(_('No PocketBook reader found'))

    # after annotations / find duplicates
    def menu_build(self):
        logger.debug('Building menu')
        # self.menu.clear()
        m = self.menu

        # objectnames preceded by pb_ are dis/enabled on connect

        self.deviceinfo = self.create_menu_action(m,
                                                  unique_name='nodevice',
                                                  text=_('No PocketBook reader found'),
                                                  icon=None
                                                  )
        self.deviceinfo.setEnabled(False)

        self.pbupload = self.create_menu_action(m,
                                                unique_name='pb_upload',
                                                text=_('Send acsm or app/dic/pbi/font file(s) to device') + '…',
                                                icon=QIcon(I('sync.png')),
                                                triggered=self.show_upload,
                                                )
        self.pbupload.setObjectName('pb_upload')

        self.pbbackup = self.create_menu_action(m,
                                                unique_name='pb_backup',
                                                text=_('Backup device database(s)') + '…',
                                                icon=QIcon(I('save.png')),
                                                triggered=self.show_backup_annotations,
                                                )
        self.pbbackup.setObjectName('pb_backup')

        self.pbexporthighlights = self.create_menu_action(m,
                                                          unique_name='pb_exporthighlights',
                                                          text=_('Export highlights to HTML') + '…',
                                                          icon=QIcon(I('save.png')),
                                                          triggered=self.show_exporthighlights,
                                                          )
        self.pbexporthighlights.setObjectName('pb_exporthighlights')

        self.pbmergefix_annotations = self.create_menu_action(m,
                                                              unique_name='pb_merge_anns',
                                                              text=_('Merge/fix annotations on device') + '…',
                                                              icon=QIcon(I('')),
                                                              triggered=self.show_mergefix_annotations,
                                                              )
        self.pbmergefix_annotations.setObjectName('pb_mergefix_annotations')

        m.addSeparator()

        self.create_menu_action(m,
                                unique_name='configure',
                                text=_('Customize plugin') + '…',
                                icon=QIcon(I('config.png')),
                                triggered=self.show_configuration
                                )

        self.create_menu_action(m,
                                unique_name='help',
                                text=_('Help') + '…',
                                icon=QIcon(I('help.png')),
                                triggered=self.show_help
                                )

        self.create_menu_action(m,
                                unique_name='about',
                                text=_('About') + '…',
                                icon=get_icons(PLUGIN_ICONS[0]),
                                triggered=self.show_about
                                )

    def show_help(self):
        logger.debug('Starting...')

        # borrowed from kobo utilities sans language support
        def get_help_file_resource():
            # We will write the help file out every time, in case the user upgrades the plugin zip
            # and there is a later help file contained within it.
            HELP_FILE = 'PocketBook-Tools_Help_en.html'
            file_data = self.load_resources('help/' + HELP_FILE)['help/' + HELP_FILE]
            file_path = os.path.join(config_dir, 'plugins', HELP_FILE)
            with open(file_path, 'wb') as f:
                f.write(file_data)
            return file_path

        url = 'file:///' + get_help_file_resource()
        logger.debug('Help url: %s' % url)
        open_url(QUrl(url))

    def show_about(self):
        logger.debug('Starting...')
        version = self.interface_action_base_plugin.version
        title = "%s v %d.%d.%d" % (self.name, version[0], version[1], version[2])
        text = (_('To learn more about this plugin, visit the '
                 '<a href="%s">plugin thread</a> '
                 'at MobileRead’s Calibre forum.') % URLMR)
        report = get_resources('about.txt').decode('utf-8')
        d = MessageBox(MessageBox.INFO, title, text, det_msg=report, show_copy_button=False)
        d.exec_()

    def show_upload(self):
        logger.debug('Starting...')
        filefilters = [(_("Supported files"), ['ttf', 'otf', 'app', 'pbi', 'dic', 'acsm']), ]
        zipenabled = prefs['up_zipenabled'] if calibre_version >= (4, 99, 0) else False
        if zipenabled:
            filefilters[0][1].append('zip')

        files = choose_files(window=self.gui, name='uploadselect',
                             title='Choose one or more files',
                             filters=filefilters,
                             all_files=False)
        if not files:
            return

        # COPY
        fileobjs = uploader_prep(files,
                            mainpath=self.mainpath,
                            cardpath=self.cardpath if prefs['up_acsmtocard'] else None,
                            zipenabled=zipenabled,
                            replace=prefs['up_alwaysreplace'],
                            deletemode=prefs['up_deletemode'],
                            gui=True)

        t = uploaderTW()

        rows = len(fileobjs)
        if (rows > 0):
            t.tableWidget.setRowCount(rows)

        # add objs
        for row, fileobj in enumerate(fileobjs):
            cb_copy = QTableWidgetItem(fileobj.filename)
            cb_card = QTableWidgetItem()
            cb_delete = QTableWidgetItem("ZIP" if fileobj.archive_parent else None)
            filetype = QTableWidgetItem(fileobj.filetype or '')
            msg = QTableWidgetItem(fileobj.msg or '')

            # checker.setProperty("fileobj", row)
            cb_copy.setData(100, row)
            cb_copy.setData(102, fileobj.filename)
            cb_card.setData(100, row)
            cb_delete.setData(100, row)
            cb_delete.setData(101, fileobj.archive_parent)

            if fileobj.filetype:
                cb_copy.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
            else:
                cb_copy.setFlags(Qt.ItemIsUserCheckable)

            if fileobj.process:
                cb_delete.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            else:
                cb_delete.setFlags(Qt.ItemIsUserCheckable)

            if self.cardpath and fileobj.filetype == "ACSM":
                cb_card.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            else:
                cb_card.setFlags(Qt.ItemIsUserCheckable)

            filetype.setFlags(Qt.ItemIsEnabled)
            msg.setFlags(Qt.ItemIsEnabled)

            cb_copy.setCheckState(Qt.Checked if fileobj.process else Qt.Unchecked)
            cb_card.setCheckState(Qt.Checked if fileobj.tocard else Qt.Unchecked)
            cb_delete.setCheckState(Qt.Checked if fileobj.process and fileobj.delete and fileobj.filetype else Qt.Unchecked)

            filetype.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            if cb_delete.checkState() == Qt.Checked:
                cb_delete.setBackground(QColor('orange'))

            t.tableWidget.setItem(row, 0, cb_copy)
            t.tableWidget.setItem(row, 1, filetype)
            t.tableWidget.setItem(row, 2, cb_card)
            t.tableWidget.setItem(row, 3, msg)
            t.tableWidget.setItem(row, 4, cb_delete)

        # table settings
        t.tableWidget.sortByColumn(1, Qt.DescendingOrder)
        t.tableWidget.setSortingEnabled(True)

        # connections
        def get_tableitemchecked(item):
            return True if item.checkState() == Qt.Checked else False

        def cellclicked(item):
            fileobj_nr = item.data(100)
            row = item.row()
            col = item.column()
            if col == 0:
                checked = get_tableitemchecked(item)
                fileobjs[fileobj_nr].process = checked
                logger.debug("Fileobj.process after: %s" % fileobjs[fileobj_nr].process)
                if not checked:
                    t.tableWidget.item(row, 4).setFlags(Qt.ItemIsUserCheckable)
                else:
                    t.tableWidget.item(row, 4).setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            elif col == 2:
                checked = get_tableitemchecked(item)
                fileobjs[fileobj_nr].setroot(self.cardpath if checked else self.mainpath,
                                             tocard=checked)
                logger.debug("Fileobj.dest_full after: %s" % fileobjs[fileobj_nr].dest_full)
            elif col == 4:
                checked = get_tableitemchecked(item)
                fileobjs[fileobj_nr].delete = checked
                logger.debug('fileobj delete? %s' % fileobjs[fileobj_nr].delete)

                archive_parent = item.data(101)
                if not archive_parent:
                    fileobjs[fileobj_nr].delete = checked
                else:
                    logger.debug('toggling delete for archive items of: %s' % archive_parent)
                    # should use model/index, but works for now
                    for nrow in range(t.tableWidget.rowCount()):
                        item2 = t.tableWidget.item(nrow, col)
                        if item2.data(101) == archive_parent:
                            # t.tableWidget.item(nrow, col).setCheckState(Qt.Checked if checked else Qt.Unchecked)
                            item2.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                            fileobjs[item2.data(100)].delete = checked

        def cellchanged(item):
            if item.data(102):
                infocell = t.tableWidget.item(item.row(), 3)
                if item.text() != item.data(102):
                    # extension check...
                    item.setBackground(Qt.yellow)
                    infocell.setBackground(Qt.yellow)
                    infocell.setText('Filename (was) changed (user)')
                    fileobjs[item.data(100)].dest_filename = item.text()
                    logger.debug('Renamed dest_full: %s' % fileobjs[item.data(100)].dest_full)
                else:
                    item.setBackground(Qt.white)
                    infocell.setBackground(Qt.white)

        t.tableWidget.itemClicked.connect(cellclicked)
        t.tableWidget.itemChanged.connect(cellchanged)

        temp = t.exec_()

        if temp:
            report, copycount = uploader_copy(fileobjs,
                                gui=True)
        else:
            return

        d = MessageBox(MessageBox.INFO, "Upload(s) finished", '%d files uploaded (details below):' % copycount,
                       det_msg=report, show_copy_button=True)
        d.exec_()


    def show_backup_annotations(self):
        logger.debug('Starting...')

        exportdir = choose_dir(self.gui, 'backupdir', title='Choose backup directory')
        if not exportdir:
            return

        copiedfiles = []
        notcopiedfiles = []

        # backup explorer
        logger.debug('Starting backup for: %s' % self.explorerdbpath)
        copied = dbbackup('defaultroot', self.explorerdbpath, exportdir, labeltime=True)
        if copied:
            copiedfiles += [self.explorerdbpath]
        else:
            notcopiedfiles += [self.explorerdbpath]

        # backup books.db
        for profile, path in self.bookdbs:
            if not prefs['bk_include_emptybookdb'] and sqlite_execute_query(
                    path, r"SELECT COUNT(*) FROM Tags WHERE TagID == 102")[0] < 1:
                logger.debug('Skipping bookdb backup: %s' % path)
                continue
            logger.debug('Starting backup for: %s' % path)
            copied = dbbackup(profile, path, exportdir, labeltime=True)
            if copied:
                copiedfiles += [path]
            else:
                notcopiedfiles += [path]

        logger.debug('copied files: %s' % (copiedfiles))
        logger.debug('notcopied files: %s' % (notcopiedfiles))
        
        text = 'Nothing exported'
        report = ''
        if copiedfiles:
            text = 'Exported %d database(s) to:<br />' \
                   '<a href=\'file:%s\'>%s</a>' % (len(copiedfiles), exportdir, exportdir)
            for db in copiedfiles:
                report += 'Copied: %s\n' % db
            report += '\n\n' if notcopiedfiles else ''
        if notcopiedfiles:
            for db in notcopiedfiles:
                report += 'FAILED: %s\n' % db

        d = MessageBox(MessageBox.INFO, 'Database(s) backup finished',
                       text, det_msg=report,
                       show_copy_button=True)
        d.exec_()

    def show_exporthighlights(self):
        logger.debug('Starting...')

        text = 'Exported highlights to:<br/>'
        exportedfiles = []
        filefilters = [('HTML', ['html', 'htm'])]
        for profile, path in self.bookdbs:
            if sqlite_execute_query(
                    path, r"SELECT COUNT(*) FROM Tags WHERE TagID = 102 and Val <> 'bookmark'")[0] < 1:
                continue

            savefile = choose_save_file(window=self.gui, name='noteexportfiles',
                                        title='Choose export file for %s books.db file' % profile,
                                        filters=filefilters,
                                        all_files=False,
                                        initial_path=None,
                                        initial_filename='pocketbook-highlights_export-%s.html' % profile
                                        )
            if not savefile:
                logger.debug('Cancelling export for %s' % path)
                continue
            elif not savefile.lower().endswith(('.html', '.htm')):
                savefile += '.html'

            logger.debug('Starting export for: %s' % path)
            highlightcount = export_htmlhighlights(path,
                                                   outputfile=savefile,
                                                   sortontitle=prefs['hl_sortdate']
                                                   )

            if highlightcount:
                exportedfiles.append(savefile)
                text += '<a href=\'file:%s\'>%s</a> (%d highlights)<br/>' % (savefile, savefile, highlightcount)
                logger.debug('exportedfile %s has count %d' % (exportedfiles, highlightcount))

        if not exportedfiles:
            text = 'No annotations exported / to export'
        d = MessageBox(MessageBox.INFO, 'Highlight export finished',
                       text, det_msg=None,
                       show_copy_button=False)
        d.exec_()

    def show_mergefix_annotations(self):
        text = 'This tool will modify the device\'s annotation database(s).<br /><br />' \
               '<b>Please backup the \'books.db\' database(s) first.</b><br /><br />' \
               'Continue?'
        d = question_dialog(None, 'Warning',
                            text, det_msg=None,
                            show_copy_button=False,
                            default_yes=False,
                            override_icon=QIcon(I('dialog_warning.png')))
        if not d:
            return

        report = ''
        changedrowsum = 0
        for profile, path in self.bookdbs:
            if sqlite_execute_query(path,
                                        r"SELECT COUNT(*) FROM Tags WHERE TagID = 102 and Val <> 'bookmark'")[0] < 1:
                continue

            titledupes_count = sqlite_execute_query(path,
                                                    'SELECT COUNT(*) as title_dupes FROM (SELECT OID FROM Books'
                                                    ' GROUP BY Title, Authors HAVING COUNT(*) > 1)')[0]
            logger.debug('books.db has %s duplicate title' % titledupes_count)
            if not titledupes_count:
                report += 'Nothing found to fix for %s<br />.' % db
            else:
                report += 'Starting inspection of \'%s\':\n\n' % path
                output, changedrows = mergefix_annotations(path)
                report += output
                changedrowsum += changedrows

        if changedrowsum:
            text = '%d rows changed.<br /><br />Please check details below.' % changedrowsum
        else:
            text = 'No annotations found to merge/fix.'

        d = MessageBox(MessageBox.INFO, 'Finished merge/fix annotations',
                       text, det_msg=report,
                       show_copy_button=True)
        d.exec_()

    def show_configuration(self):
        logger.debug('Starting...')
        self.interface_action_base_plugin.do_user_config(self.gui)

    def apply_settings(self):
        from calibre_plugins.pocketbook_tools.config import prefs
        #prefs

        if prefs['debug']:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
