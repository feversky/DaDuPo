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

from functools import partial

from PySide2 import QtCore, QtWidgets
from PySide2.QtCore import Qt
from PySide2.QtWidgets import QWidget, QTableWidget, QHBoxLayout, QDialog, QTableWidgetItem, QSpinBox, QComboBox, \
    QVBoxLayout, QAbstractItemView

from data.DataPool import DataPool, SignalConfig
import pyqtgraph as pg

from device.DeviceManager import DeviceManager
from device.XcpClient import XcpClient
from icon.icon import Icon

# for Xcp Signal & Parameter only
class MeasurementConfigDialog(QDialog):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowIcon(Icon.settings())
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels(['Name', 'Channel', 'Rate[ms]'])
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.autoFillBackground()
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(self.table_widget)
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.set_data)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.setModal(True)
        self.setWindowTitle('Measurement Configuration')
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        self.data_pool = DataPool()
        self.device_manager = DeviceManager()
        self.table_widget.setRowCount(len(self.data_pool.signal_config))
        self.table_widget.itemSelectionChanged.connect(self._set_selection)
        self.table_widget.cellChanged.connect(self._cell_changed)
        self._prev_checked_state = []
        self._selected_rows = []
        self._prev_selected_rows = []
        for i, (sid, config) in enumerate(self.data_pool.signal_config.items()):
            obj = self.data_pool.get_obj_by_sid(sid)
            db_name = obj.parent.name
            dev: XcpClient = self.device_manager.get_device_by_db_name(db_name)
            channels = list(dev.get_daq_event_channels().keys())
            channels.append('polling')
            chk_box = QTableWidgetItem(sid.split('/')[-1])
            chk_box.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_box.setCheckState(Qt.Checked if config.enabled else Qt.Unchecked)
            chk_box.setData(Qt.UserRole, sid)
            self._prev_checked_state.append(chk_box.checkState())
            rate_sb = QSpinBox()
            rate_sb.setSpecialValueText("--")
            rate_sb.setMinimum(0)
            rate_sb.setMaximum(100000)
            rate_sb.setSingleStep(10)
            if config.channel == 'polling':
                rate_sb.setValue(config.rate)
            channel_cb = pg.ComboBox(items=channels)

            def on_value_changed(current_row, val):
                for row in set(list(self._prev_selected_rows) + [current_row]):
                    combobox = self.table_widget.cellWidget(row, 1)
                    if not combobox:
                        return
                    combobox.setValue(val)
                    spinbox = self.table_widget.cellWidget(row, 2)
                    if val != 'polling':
                        spinbox.setValue(0)
                    elif spinbox.value() == 0:
                        spinbox.setValue(100)
                    spinbox.setEnabled(val == 'polling')

            channel_cb.currentTextChanged.connect(partial(on_value_changed, i))
            channel_cb.setValue(config.channel)

            self.table_widget.setItem(i, 0, chk_box)
            self.table_widget.setCellWidget(i, 1, channel_cb)
            self.table_widget.setCellWidget(i, 2, rate_sb)

    def set_data(self):
        self.accept()
        cfg = {}
        for i in range(self.table_widget.rowCount()):
            sid = self.table_widget.item(i, 0).data(Qt.UserRole)
            enabled = self.table_widget.item(i, 0).checkState() == Qt.CheckState.Checked
            channel = self.table_widget.cellWidget(i, 1).value()
            rate = self.table_widget.cellWidget(i, 2).value()
            cfg[sid] = SignalConfig(sid, channel, rate, enabled)
        self.data_pool.signal_config = cfg

    def _set_selection(self):
        self._prev_selected_rows = self._selected_rows
        self._selected_rows = set([sel.row() for sel in self.table_widget.selectedIndexes()])

    def _cell_changed(self):
        for i in range(self.table_widget.rowCount()):
            item = self.table_widget.item(i, 0)
            if not item:
                return
            current_state = item.checkState()
            if current_state != self._prev_checked_state[i]:
                self._prev_checked_state[i] = current_state
                for row in self._prev_selected_rows:
                    it = self.table_widget.item(row, 0)
                    it.setCheckState(current_state)
                break
