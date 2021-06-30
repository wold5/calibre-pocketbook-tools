from calibre.utils.config import JSONConfig
from calibre.constants import numeric_version as calibre_version

try:
    from PyQt5.Qt import (Qt, QCheckBox, QGridLayout, QGroupBox, QIcon,
                          QHBoxLayout, QVBoxLayout, QWidget, pyqtSignal, QLabel, QComboBox)
except ImportError as e:
    print('Problem loading QT5: ', e)
    from PyQt4.Qt import (Qt, QCheckBox, QGridLayout, QGroupBox, QIcon,
                          QHBoxLayout, QVBoxLayout, QWidget, pyqtSignal, QLabel, QComboBox)

import logging
logger = logging.getLogger('pbt_logger.config')
# TODO

prefs = JSONConfig('plugins/pocketbook_tools')

# Set defaults
prefs.defaults['up_zipenabled'] = True
prefs.defaults['up_acsmtocard'] = False
prefs.defaults['up_alwaysreplace'] = True
prefs.defaults['up_deletemode'] = 0
prefs.defaults['bk_include_emptybookdb'] = False
prefs.defaults['hl_sortdate'] = 0
prefs.defaults['debug'] = False


class ConfigWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.l = QVBoxLayout()
        self.setLayout(self.l)

        # Uploader options
        self.cfg_runtime_options_gb = QGroupBox(_('Uploader options'))
        self.cfg_runtime_options_qup = QVBoxLayout(self.cfg_runtime_options_gb)
        self.l.addWidget(self.cfg_runtime_options_gb)

        self.up_alwaysreplace = QCheckBox(_('Always replace existing files (if different)'))
        # self.up_alwaysreplace.setObjectName('up_alwaysreplace')
        self.up_alwaysreplace.setToolTip(_('Always mark existing files for copying, unless they are identical.'))
        self.up_alwaysreplace.setChecked(prefs['up_alwaysreplace'])
        self.cfg_runtime_options_qup.addWidget(self.up_alwaysreplace)

        self.up_zipenabled = QCheckBox(_('Enable importing from .zip files'))
        self.up_zipenabled.setToolTip(_('Omits file metadata (date) on Windows.'))
        self.up_zipenabled.setChecked(prefs['up_zipenabled'])
        # zip .filename requires Python 3.6>
        if calibre_version < (4, 99, 0):
            self.up_zipenabled.setEnabled(False)
            self.up_zipenabled.setCheckable(False)
        self.cfg_runtime_options_qup.addWidget(self.up_zipenabled)

        self.up_acsmtocard = QCheckBox(_('Try copy .acsm files to SD-card (if available)'))
        self.up_acsmtocard.setToolTip(_('If an SD-card is present, copy .acsm files there, otherwise to main memory.'))
        self.up_acsmtocard.setChecked(prefs['up_acsmtocard'])
        self.cfg_runtime_options_qup.addWidget(self.up_acsmtocard)

        self.up_deletemode_hbox = QHBoxLayout()
        self.up_deletemode_hbox.setObjectName('Delete options Hbox')
        self.cfg_runtime_options_qup.addLayout(self.up_deletemode_hbox)

        self.hl_sortdate_label = QLabel('Mark source file for deletion:')
        # self.cfg_runtime_options_qex.addWidget(self.hl_sortdate_label)
        self.up_deletemode_hbox.addWidget(self.hl_sortdate_label)

        self.up_deletemode_comboBox = QComboBox(self.cfg_runtime_options_gb)
        self.up_deletemode_comboBox.addItem('Never')
        self.up_deletemode_comboBox.addItem('Only .acsm files')
        self.up_deletemode_comboBox.addItem('Only .acsm or .zip (parent) files')
        self.up_deletemode_comboBox.addItem('Any sendable filetype')
        self.up_deletemode_comboBox.setCurrentIndex(prefs['up_deletemode'])
        self.up_deletemode_comboBox.setItemIcon(3, QIcon(I('dialog_warning.png')))
        self.up_deletemode_hbox.addWidget(self.up_deletemode_comboBox)

        # General options
        self.cfg_runtime_options_gb = QGroupBox(_('Backup options'))
        self.cfg_runtime_options_qbk = QVBoxLayout(self.cfg_runtime_options_gb)
        self.l.addWidget(self.cfg_runtime_options_gb)

        self.bk_include_emptybookdb = QCheckBox(_('Export books.db(s) without annotations'))
        self.bk_include_emptybookdb.setToolTip(_('Books.db databases are (currently) used for storing annotations.'))
        self.bk_include_emptybookdb.setChecked(prefs['bk_include_emptybookdb'])
        self.cfg_runtime_options_qbk.addWidget(self.bk_include_emptybookdb)

        # export options
        self.cfg_runtime_options_gb = QGroupBox(_('Export options'))
        self.cfg_runtime_options_gb.setObjectName('Export options')
        self.l.addWidget(self.cfg_runtime_options_gb)  # add widget

        self.cfg_runtime_options_qex = QVBoxLayout(self.cfg_runtime_options_gb)
        self.cfg_runtime_options_qex.setObjectName('Export group Vbox')

        self.hl_sortdate_hbox = QHBoxLayout()
        self.hl_sortdate_hbox.setObjectName('Export options Hbox')
        self.cfg_runtime_options_qex.addLayout(self.hl_sortdate_hbox)

        self.hl_sortdate_label = QLabel('Sort exported highlights by:')
        # self.cfg_runtime_options_qex.addWidget(self.hl_sortdate_label)
        self.hl_sortdate_hbox.addWidget(self.hl_sortdate_label)

        self.hl_sortdate_comboBox = QComboBox(self.cfg_runtime_options_gb)
        self.hl_sortdate_comboBox.addItem('Annotation date')
        self.hl_sortdate_comboBox.addItem('Title and Page')
        self.hl_sortdate_comboBox.setCurrentIndex(prefs['hl_sortdate'])
        self.hl_sortdate_hbox.addWidget(self.hl_sortdate_comboBox)

        # Other options
        self.cfg_runtime_options_gb = QGroupBox(_('Other options'))
        self.cfg_runtime_options_gb.setObjectName('Other options')
        self.l.addWidget(self.cfg_runtime_options_gb)
        self.cfg_runtime_options_gn = QVBoxLayout(self.cfg_runtime_options_gb)

        self.gn_debug = QCheckBox(_('Enable debug logging to console (no restart required)'))
        self.gn_debug.setToolTip(_('Log debug messages to console.'))
        self.gn_debug.setChecked(prefs['debug'])
        self.cfg_runtime_options_gn.addWidget(self.gn_debug)

    # todo, currently always saves on exit -> use clicked.connect
    def save_settings(self):
        prefs['up_zipenabled'] = self.up_zipenabled.isChecked()
        prefs['up_acsmtocard'] = self.up_acsmtocard.isChecked()
        prefs['up_alwaysreplace'] = self.up_alwaysreplace.isChecked()
        prefs['up_deletemode'] = self.up_deletemode_comboBox.currentIndex()
        prefs['bk_include_emptybookdb'] = self.bk_include_emptybookdb.isChecked()
        prefs['hl_sortdate'] = self.hl_sortdate_comboBox.currentIndex()
        prefs['debug'] = self.gn_debug.isChecked()
        logger.debug(prefs)
