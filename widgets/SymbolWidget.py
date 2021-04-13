__copyright__ = """
    DaDuPo - An online calibration and measurement tool using XCP protocol

    (C) 2021 by Jun Yang <fever_sky@qq.com>

    All Rights Reserved

    This file is part of DaDuPo.

    DaDuPo is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from PySide2.QtCore import Qt, QMimeData, Signal
from PySide2.QtGui import QDrag, QMouseEvent, QIcon
from PySide2.QtWidgets import QWidget, QVBoxLayout, QLineEdit, \
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QMenu, QAction, QHeaderView

from data.Asap2Database import Asap2Database, ParameterType
from icon.icon import Icon
from widgets.BaseUIEvents import BaseUIEvents


class MyQTreeWidget(QTreeWidget):
    mouse_moved = Signal(QMouseEvent)
    mouse_clicked = Signal(str)

    def mouseMoveEvent(self, event):
        self.mouse_moved.emit(event)
        QTreeWidget.mouseMoveEvent(self, event)

    def mouseDoubleClickEvent(self, event):
        data = next((si.data(0, Qt.UserRole) for si in self.selectedItems()), None)
        if data:
            self.mouse_clicked.emit(data)


class SymbolWidget(BaseUIEvents, QWidget):

    def __init__(self, database=None, parent=None, dialog_mode=False):
        QWidget.__init__(self, parent)

        if database is None:
            database = []
        self.database = database
        self.dialog_mode = dialog_mode
        layout = QVBoxLayout()
        self.setLayout(layout)
        self._filter = ""
        self._selected = []

        self.inputFilter = QLineEdit()
        self.inputFilter.setText(self._filter)
        self.inputFilter.textChanged.connect(self.onFilterChanged)
        layout.addWidget(self.inputFilter)

        self.treeWidget = MyQTreeWidget()
        self.treeWidget.mouse_moved.connect(self.mouse_moved_handler)
        self.treeWidget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.treeWidget.setColumnCount(3)
        self.treeWidget.setHeaderLabels(['Name', 'Node', 'Comment'])
        # self.treeWidget.setColumnWidth(0, 400)
        # self.treeWidget.setColumnWidth(1, 100)
        # self.treeWidget.setSortingEnabled(True)
        self.treeWidget.header().setResizeMode(QHeaderView.ResizeToContents)
        self.treeWidget.header().setStretchLastSection(False)
        # if not dialog_mode:
        #     self.treeWidget.setDragDropMode(QAbstractItemView.DragDrop)
        self.updateTreeView()
        layout.addWidget(self.treeWidget)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def mouse_moved_handler(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if self.dialog_mode:
            return
        selected = '---'.join(self.getSelectedSignals())
        if not selected:
            return
        mimeData = QMimeData()
        mimeData.setText(selected)

        # pixmap = QPixmap(self.size())
        # self.render(pixmap)

        drag = QDrag(self)
        drag.setMimeData(mimeData)
        # drag.setPixmap(pixmap)
        # drag.setHotSpot(hotSpot)

        drag.exec_(Qt.CopyAction, Qt.CopyAction)

    def updateTreeView(self):
        self.treeWidget.clear()
        tree_root = self.treeWidget.invisibleRootItem()
        for db in self.database:
            if type(db) is Asap2Database:
                db_name = db.name
            else:
                raise Exception(f'{type(db)} is not implemented')
            db_node = QTreeWidgetItem(tree_root, [db_name])
            db_node.setIcon(0, Icon.database())
            db_node.setFirstColumnSpanned(True)
            tree_root.addChild(db_node)
            db_node.setFlags(db_node.flags() & ~Qt.ItemIsSelectable)
            if type(db) is Asap2Database:
                a2l: Asap2Database = db
                ch_node = QTreeWidgetItem(db_node, ['Parameters'])
                ch_node.setFlags(ch_node.flags() & ~Qt.ItemIsSelectable)
                db_node.addChild(ch_node)
                parameters = [c for c in a2l.asap2_parameters]
                for c in parameters:
                    if self._filter in c.name.lower():
                        c_node = QTreeWidgetItem(ch_node, [c.name, '', c.description])
                        sid = '/'.join([a2l.name, c.name])
                        c_node.setData(0, Qt.UserRole, sid)
                        if c.parameter_type == ParameterType.ASCII:
                            c_node.setIcon(0, Icon.string())
                        elif c.parameter_type == ParameterType.VALUE:
                            c_node.setIcon(0, Icon.parameter())
                        elif c.parameter_type == ParameterType.MAP:
                            c_node.setIcon(0, Icon.parameter_map())
                        else:
                            c_node.setIcon(0, Icon.parameter_curve())
                        ch_node.addChild(c_node)
                sig_node = QTreeWidgetItem(db_node, ['Signals'])
                sig_node.setFlags(sig_node.flags() & ~Qt.ItemIsSelectable)
                db_node.addChild(sig_node)
                measurements = [s for s in a2l.asap2_signals]
                for m in measurements:
                    if self._filter in m.name.lower():
                        m_node = QTreeWidgetItem(sig_node, [m.name, '', m.description])
                        sid = '/'.join([a2l.name, m.name])
                        m_node.setData(0, Qt.UserRole, sid)
                        if m.count == 1:
                            m_node.setIcon(0, Icon.signal())
                        else:
                            m_node.setIcon(0, Icon.signal_array())
                        sig_node.addChild(m_node)

        if self._filter:
            self.treeWidget.expandAll()
        else:
            proxy = self.treeWidget.model()
            for row in range(proxy.rowCount()):
                index = proxy.index(row, 0)
                self.treeWidget.expand(index)
        # self.treeWidget.sortItems(0, QtCore.Qt.SortOrder.AscendingOrder)

    def onFilterChanged(self):
        self._filter = self.inputFilter.text().lower()
        self.updateTreeView()

    def getSelectedSignals(self):
        return [si.data(0, Qt.UserRole) for si in self.treeWidget.selectedItems()]
