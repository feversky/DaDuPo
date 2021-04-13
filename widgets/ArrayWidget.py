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

from PySide2 import QtWidgets
from PySide2.QtCore import Qt
from PySide2.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem

from data.Asap2Database import Asap2Parameter, ParameterType
from data.DataPool import DataPool
from widgets.BaseUIEvents import BaseUIEvents
import pyqtgraph as pg


class ArrayWidgetBase(BaseUIEvents, QWidget):
    def __init__(self, sid=None, parent=None):
        QWidget.__init__(self, parent)
        self.sid = sid
        self.data_pool = DataPool()

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.table = QTableWidget(self)
        self.layout.addWidget(self.table)

        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.setShowGrid(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        if sid:
            self.set_array(sid)

    def get_config(self):
        return self.sid

    def set_array(self, sid):
        pass

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and not self.sid:
            obj = self.data_pool.get_obj_by_sid(event.mimeData().text())
            if obj.count > 0:
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        if event.mimeData().hasText():
            self.sid = event.mimeData().text()
            self.set_array(self.sid)
        else:
            event.ignore()


class ArrayParameterWidget(ArrayWidgetBase):
    def __init__(self, sid=None, parent=None):
        ArrayWidgetBase.__init__(self, sid, parent)
        self.prev_data = None
        self.cur_data = None
        self.obj = None
        self.setEnabled(False)

    def set_array(self, sid):
        # todo: display unit
        obj = self.data_pool.get_obj_by_sid(sid)
        if not obj:
            return
        self.obj = obj
        self.setWindowTitle(obj.name)
        self.table.itemChanged.connect(self.on_item_changed)
        if type(obj) is Asap2Parameter and obj.ref_x_ref and obj.ref_y_ref:
            self.table.setRowCount(obj.ref_y_ref.count)
            self.table.setColumnCount(obj.ref_x_ref.count)
        else:
            self.table.setColumnCount(obj.count)
            self.table.setRowCount(2)
            self.graph_view = pg.GraphicsView()
            pi = pg.PlotItem()
            self.graph_view.setCentralWidget(pi)
            self.viewbox = pi.getViewBox()
            self.plot_item = pg.PlotDataItem(size=8, symbol='o')
            self.viewbox.addItem(self.plot_item)
            self.layout.addWidget(self.graph_view)
        self.update_data()

    def update_data(self):
        if not self.obj:
            return
        if not self.xcp_client.connected:
            return
        self.setEnabled(True)
        obj = self.obj
        phy_data = self.xcp_client.upload(obj.Name)[-1]
        self.prev_data = phy_data
        if obj.Type == ParameterType.VAL_BLK:
            for i, d in enumerate(phy_data):
                item = QTableWidgetItem(str(i))
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                self.table.setItem(0, i, item)
                self.table.setItem(1, i, QTableWidgetItem(str(d)))
            self.plot_item.setData(list(range(len(phy_data))), phy_data)
            return
        if obj.y_dimension() > 1:
            for i, d in enumerate(phy_data):
                self.table.setItem(0, i, QTableWidgetItem(d))
        elif obj.Type == ParameterType.CURVE:
            y_data = phy_data[-1]
            if obj.AXIS_DESCR[0].Attribute == AXIS_DESCR_Attribute.COM_AXIS:
                axis = self.get_axis_pts(obj.AXIS_DESCR[0].AXIS_PTS_REF.AxisPoints)
                axis_data = self.xcp_client.upload(axis.Name)[-1]
            else:
                axis_data, y_data = phy_data
            self.prev_data = phy_data
            axis_readonly = obj.AXIS_DESCR[0].Attribute == AXIS_DESCR_Attribute.FIX_AXIS
            if obj.RECORD_LAYOUT.DIST_OP_X or obj.RECORD_LAYOUT.OFFSET_X or obj.RECORD_LAYOUT.SHIFT_OP_X:
                axis_readonly = True
            for i, d in enumerate(axis_data):
                item = QTableWidgetItem(str(d))
                if axis_readonly:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(0, i, item)
                self.table.setItem(1, i, QTableWidgetItem(str(y_data[i])))
            self.plot_item.setData(axis_data, y_data)

    def get_axis_pts(self, name):
        return next(a for m in self.data_pool.a2l.PROJECT.MODULE for a in m.AXIS_PTS if a.Name == name)

    def on_device_connected(self):
        self.setEnabled(True)
        self.update_data()

    def on_device_disconnected(self):
        self.setEnabled(False)

    def on_item_changed(self, item: QTableWidgetItem):
        index = self.table.indexFromItem(item)
        row, col = index.row(), index.column()
        obj = self.obj
        if obj.Type == ParameterType.CURVE:
            old_data = self.prev_data[row][col]
            new_data = type(old_data)(item.text())
            if old_data != new_data:
                if obj.AXIS_DESCR[0].Attribute == AXIS_DESCR_Attribute.COM_AXIS:
                    if row == 0:
                        axis = self.get_axis_pts(obj.AXIS_DESCR[0].AXIS_PTS_REF.AxisPoints)
                        byts = Asap2Util.single_phy_value_to_bytes(new_data, axis.data_type(),
                                                                   axis.BYTE_ORDER.ByteOrder, axis.COMPU_METHOD)
                        offset = Asap2Util.calc_deposit_from_datatype(axis.data_type(), axis.RECORD_LAYOUT) * col
                        addr = axis.Address + offset
                    else:
                        byts = Asap2Util.single_phy_value_to_bytes(new_data, obj.RECORD_LAYOUT.FNC_VALUES.Datatype,
                                                                   obj.BYTE_ORDER.ByteOrder, obj.COMPU_METHOD)
                        offset = Asap2Util.calc_deposit_from_datatype(obj.RECORD_LAYOUT.FNC_VALUES.Datatype,
                                                                      obj.RECORD_LAYOUT) * col
                        addr = obj.Address + offset
                    self.xcp_client.download_bytes(addr, byts)
                    self.update_data()
                elif obj.AXIS_DESCR[0].Attribute == AXIS_DESCR_Attribute.STD_AXIS:
                    # fixed axis was done by set axis to readonly before
                    layout = Asap2Util.calc_layout(obj.RECORD_LAYOUT, len(self.prev_data[0]))
                    if row == 0:
                        offset = Asap2Util.calc_deposit_from_datatype(obj.RECORD_LAYOUT.AXIS_PTS_X.Datatype,
                                                                      obj.RECORD_LAYOUT) * col
                        addr = layout[AXIS_PTS_X] + offset
                        byts = Asap2Util.single_phy_value_to_bytes(new_data, obj.RECORD_LAYOUT.AXIS_PTS_X.Datatype,
                                                                   obj.BYTE_ORDER.ByteOrder, obj.COMPU_METHOD)
                    else:
                        offset = Asap2Util.calc_deposit_from_datatype(obj.RECORD_LAYOUT.FNC_VALUES.Datatype,
                                                                      obj.RECORD_LAYOUT) * col
                        addr = layout[FNC_VALUES] + offset
                        byts = Asap2Util.single_phy_value_to_bytes(new_data, obj.RECORD_LAYOUT.FNC_VALUES.Datatype,
                                                                   obj.BYTE_ORDER.ByteOrder, obj.COMPU_METHOD)
                    self.xcp_client.download_bytes(addr, byts)
                    self.update_data()
