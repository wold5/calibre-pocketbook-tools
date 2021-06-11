from calibre.constants import numeric_version as calibre_version
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.device import device_signals
from calibre.gui2 import info_dialog, error_dialog, question_dialog, open_url

try:
    from PyQt5.Qt import (Qt, QApplication, pyqtSignal, QIcon, QMenu, QAction, QRegExp, QUrl)
except ImportError as e:
    print('Problem loading QT5: ', e)
    from PyQt4.Qt import (Qt, QApplication, pyqtSignal, QIcon, QMenu, QAction, QRegExp, QUrl)

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
    fileuploader, export_htmlhighlights, dbbackup, \
    copyfile, mergefix_annotations

# logging
import logging, logging.config

# logging.config.fileConfig(load_resources('logging.conf'))
logger = logging.getLogger('pbt_logger')
logger.setLevel(logging.DEBUG if prefs['debug'] else logging.INFO)
console = logging.StreamHandler()
console.setFormatter(
    logging.Formatter('%(levelname)s - %(filename)s:%(lineno)d:%(funcName)s - %(message)s'))  # %(relativeCreated)d
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
            if getattr(self.connected_device, 'VENDOR_ID', 0) == [0xfffe]:
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
        actions = self.menu.findChildren(QAction, QRegExp('pb_.*'))
        for action in actions:
            action.setEnabled(present)

        if present:
            self.deviceinfo.setText(_('Found PocketBook. Driver: %s' % self.connected_device.name or 'Unknown'))
        else:
            self.deviceinfo.setText(_('No PocketBook reader found'))

    # borrowed from annotations / find duplicates
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
        msg = (_('To learn more about this plugin, visit the '
                 '<a href="%s">plugin thread</a> '
                 'at MobileRead’s Calibre forum.') % URLMR)
        about_text = get_resources('about.txt').decode('utf-8')
        d = MessageBox(MessageBox.INFO, title, msg, det_msg=about_text, show_copy_button=False)
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

        text = fileuploader(files,
                            mainpath=self.mainpath,
                            cardpath=self.cardpath if prefs['up_acsmtocard'] else None,
                            zipenabled=zipenabled,
                            replace=prefs['up_alwaysreplace'],
                            deletemode=prefs['up_deletemode'],
                            gui=True)

        d = MessageBox(MessageBox.INFO, "Upload(s) finished", 'Details:',
                       det_msg=text, show_copy_button=True)
        d.exec_()

    def show_backup_annotations(self):
        logger.debug('Starting...')

        exportdir = choose_dir(self.gui, 'backupdir', title='Choose backup directory')
        if not exportdir:
            return

        copiedfiles = []

        # backup explorer
        logger.debug('Starting backup for: %s' % self.explorerdbpath)
        copied = dbbackup('defaultroot', self.explorerdbpath, exportdir, labeltime=True)
        if copied:
            copiedfiles += [self.explorerdbpath]

        # backup books.db
        for profile, path in self.bookdbs:
            if not prefs['bk_include_emptybookdb'] and not sqlite_execute_query(
                    path, r"SELECT COUNT(*) FROM Tags WHERE TagID == 102"):
                logger.debug('Skipping bookdb backup: %s' % path)
                continue
            logger.debug('Starting backup for: %s' % path)
            copied = dbbackup(profile, path, exportdir, labeltime=True)
            if copied:
                copiedfiles += [path]

        logger.debug('copiedfiles: %s' % copiedfiles)

        title = 'Database(s) backup finished'
        if copiedfiles:
            text = 'Exported database(s) to:<br/>'
            text += '<a href=\'%s\'>%s</a><br /><br />' % (exportdir, exportdir)
            msg = 'Copied:\n'
            for db in copiedfiles:
                msg += '%s\n' % db
        else:
            text = 'Nothing exported'
            msg = None
        d = MessageBox(MessageBox.INFO, title,
                       text, det_msg=msg,
                       show_copy_button=True)
        d.exec_()

    def show_exporthighlights(self):
        logger.debug('Starting...')

        text = 'Exported highlights to:<br/>'
        exportedfiles = []
        filefilters = [('HTML', ['html', 'htm'])]
        for profile, path in self.bookdbs:
            if not sqlite_execute_query(
                    path, r"SELECT COUNT(*) FROM Tags WHERE TagID = 102 and Val <> 'bookmark'"):
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

        logger.debug('exportedfiles: %s' % exportedfiles)

        if exportedfiles:
            text = 'Exported highlights to<br/>'
            for outfile in exportedfiles:
                text += '<a href=\'%s\'>%s</a><br/>' % (outfile, outfile)
        else:
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
        for profile, path in self.bookdbs:
            if not sqlite_execute_query(path,
                                        r"SELECT COUNT(*) FROM Tags WHERE TagID = 102 and Val <> 'bookmark'"):
                continue

        changedrows = 0
            titledupes_count = sqlite_execute_query(path,
                                                    'SELECT COUNT(*) as title_dupes FROM (SELECT OID FROM Books'
                                                    ' GROUP BY Title, Authors HAVING COUNT(*) > 1)')
            logger.debug('books.db has %s duplicate title' % titledupes_count)
            if not titledupes_count:
                report += 'Nothing found to fix for %s<br />.' % db
            else:
                report += 'Starting inspection of \'%s\':\n\n' % path
                output, changedrows = mergefix_annotations(path)
                report += output
                text += '%d rows changed.<br /><br />Please check details below.' % changedrows

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
