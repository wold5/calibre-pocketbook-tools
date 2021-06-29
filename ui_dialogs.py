try:
    from PyQt5.Qt import (QDialog, QLabel, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                          QRect, QDialogButtonBox, QCheckBox, QAbstractItemView)
except ImportError as e:
    print('Problem loading QT5: ', e)
    from PyQt4.Qt import (QDialog, QLabel, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                          QRect, QDialogButtonBox, QCheckBox, QAbstractItemView)

# UploaderTableWidget
class uploaderTW(QDialog):
    def __init__(self):
        QDialog.__init__(self)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.setWindowTitle(_('Upload files to device'))
        self.resize(790, 400)
        self.label = QLabel("Select files to upload. Filenames may be modified first.")
        self.layout.addWidget(self.label)
        self.tableWidget = QTableWidget()
        self.tableWidget.setObjectName(u"uploaderTW")
        self.tableWidget.setGeometry(QRect(0, 0, 780, 200))
        self.tableWidget.setMinimumHeight(300)
        self.tableWidget.setMinimumWidth(300)
        self.tableWidget.setColumnCount(5)
        self.tableWidget.setHorizontalHeaderLabels(('Copy file?', 'Type', 'Card?', 'Info', 'Delete?')) # , 'rowid', 'archive_parent'
        for col, width in enumerate((250, 90, 60, 280, 60)):
            self.tableWidget.setColumnWidth(col, width)
        self.tableWidget.setAlternatingRowColors(True)
        self.tableWidget.setSelectionMode(QAbstractItemView.NoSelection)
        # self.tableWidget.resizeRowsToContents()
        # self.tableWidget.resizeColumnToContents(4)
        self.layout.addWidget(self.tableWidget)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox)
