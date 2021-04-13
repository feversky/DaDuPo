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

from abc import abstractmethod
from functools import partial

import pyqtgraph as pg
from PySide2 import QtWidgets, QtGui, QtCore
from PySide2.QtCore import Qt, QTimer
from PySide2.QtWidgets import QTableWidget, \
    QTableWidgetItem, QAbstractItemView, QLineEdit, QDoubleSpinBox

from data.Asap2Database import ParameterType, Asap2Parameter, CompuMethodType, Asap2Signal
from data.DataPool import DataPool
from device.DeviceManager import DeviceManager
from widgets.BaseUIEvents import BaseUIEvents
from device.XcpClient import XcpClient


class ScalarBaseWidget(BaseUIEvents, QTableWidget):
    def __init__(self, config=None, parent=None):
        QTableWidget.__init__(self, parent)
        self.scalars = {}
        self.data_pool = DataPool()
        self.device_manager = DeviceManager()

        self.setColumnCount(3)
        self.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setAcceptDrops(True)
        if config:
            for sid in config.split('---'):
                self.add_scalar(sid)
        # self.setStyleSheet("background-color:lightgray;")

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def get_scalars(self):
        return '---'.join(self.scalars.keys())

    @abstractmethod
    def add_scalar(self, sid):
        pass

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        if event.mimeData().hasText():
            mime = event.mimeData()
            sids = mime.text().split('---')
            event.accept()
            for sid in sids:
                self.add_scalar(sid)
        else:
            event.ignore()

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key_Delete:
            for i in self.selectedItems():
                sid = self.item(i.row(), 0).data(Qt.UserRole)
                self.removeRow(i.row())
                self.scalars.pop(sid)
        else:
            super().keyPressEvent(event)


class ScalarParameterWidget(ScalarBaseWidget):

    def add_scalar(self, sid):
        if sid in self.scalars.keys():
            return
        obj = self.data_pool.get_obj_by_sid(sid)
        if not obj:
            return
        if obj.count > 1 and not (type(obj) is Asap2Parameter and obj.parameter_type == ParameterType.ASCII):
            return
        name = obj.name
        self.scalars[sid] = obj
        row = self.rowCount()
        self.insertRow(row)
        twi = QTableWidgetItem(name)
        twi.setData(Qt.UserRole, sid)
        self.setItem(row, 0, twi)
        if type(obj) is Asap2Parameter and obj.parameter_type == ParameterType.ASCII:
            line_edit = QLineEdit()
            line_edit.setEnabled(self.xcp_client.connected)
            self.setCellWidget(row, 1, line_edit)
        else:
            self.setItem(row, 2, QTableWidgetItem(obj.unit))
            dic = DataPool().get_value_table_by_sid(sid)
            # item.setData(0, Qt.UserRole, self.signal_configs[sid])
            if dic:
                combobox = pg.ComboBox(items={v: k for k, v in dic.items()})
                combobox.setMinimumWidth(150)
                combobox.setEnabled(self.device_manager.connected)
                self.setCellWidget(row, 1, combobox)

                def on_value_changed(sid, cb, val):
                    self.device_manager.download(sid, val)
                    cb.setText(self.device_manager.upload(sid))

                combobox.currentTextChanged.connect(partial(on_value_changed, sid, combobox))
            else:
                step = 1
                if obj.compu_method:
                    if obj.compu_method_ref.compu_method_type == CompuMethodType.LINEAR:
                        step = obj.compu_method_ref.coeffs.a
                spinbox = QDoubleSpinBox(self)
                spinbox.setSingleStep(step)
                spinbox.setDecimals(min(4, len(str(step).split('.')[-1]) - 1))
                # spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                spinbox.setEnabled(self.device_manager.connected)
                self.setCellWidget(row, 1, spinbox)

                def on_value_changed(var_id, sbox, val):
                    self.device_manager.download(var_id, val)
                    sbox.setValue(self.device_manager.upload(var_id)[-1])

                spinbox.valueChanged.connect(partial(on_value_changed, sid, spinbox))

        if self.device_manager.connected:
            control = self.cellWidget(row, 1)
            value = self.device_manager.upload(sid)[-1]
            if type(control) in [QLineEdit, pg.ComboBox]:
                control.setText(value)
            elif type(control) in [QDoubleSpinBox]:
                control.setValue(value)
        self.resizeRowToContents(row)
        # self.resizeRowsToContents()
        # self.resize(self.geometry().width(), self.geometry().height())

    def on_device_connected(self):
        for row in range(self.rowCount()):
            # name = self.item(row, 0).text()
            sid = self.item(row, 0).data(Qt.UserRole)
            value = self.device_manager.upload(sid)[-1]
            control = self.cellWidget(row, 1)
            control.setEnabled(True)
            if type(control) in [QLineEdit, pg.ComboBox]:
                control.setText(value)
            elif type(control) in [QDoubleSpinBox]:
                control.setValue(value)

    def on_device_disconnected(self):
        for i in range(self.rowCount()):
            control = self.cellWidget(i, 1)
            control.setEnabled(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            mime = event.mimeData()
            sids = mime.text().split('---')
            for sid in sids:
                obj = self.data_pool.get_obj_by_sid(sid)
                if type(obj) not in [Asap2Parameter, Asap2Signal]:
                    event.ignore()
                    return
            event.accept()
        else:
            event.ignore()

class ScalarSignalWidget(ScalarBaseWidget):
    def __init__(self, config=None, parent=None):
        ScalarBaseWidget.__init__(self, config, parent)
        self.setShowGrid(True)
        self.timer = QTimer()
        self.timer.timeout.connect(self._update)

    def add_scalar(self, sid):
        if sid in self.scalars.keys():
            return
        obj = self.data_pool.get_obj_by_sid(sid)
        self.scalars[sid] = obj
        row = self.rowCount()
        self.insertRow(row)
        item1 = QTableWidgetItem(obj.name)
        item1.setData(Qt.UserRole, sid)
        self.setItem(row, 0, item1)
        item2 = QTableWidgetItem()
        item2.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.setItem(row, 1, item2)
        self.setItem(row, 2, QTableWidgetItem(obj.unit))
        self.resizeRowToContents(row)
        self.data_pool.measure_signal(sid)

    def on_start_measurement(self):
        self.timer.start(10)

    def on_stop_measurement(self):
        self.timer.stop()

    def _update(self):
        for row in range(self.rowCount()):
            sid = self.item(row, 0).data(Qt.UserRole)
            item = self.item(row, 1)
            if len(self.data_pool.signal_buffer[sid]):
                item.setText(str(self.data_pool.signal_buffer[sid][-1][1]))
