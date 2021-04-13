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

from dataclasses import dataclass
from datetime import datetime
from random import randint
from typing import Union, List

import typing
from PySide2 import QtCore, QtWidgets, QtGui
from PySide2.QtCore import Qt, Slot, Signal, QTimer
from PySide2.QtGui import QColor
from PySide2.QtWidgets import QFrame, QDialog, QWidget, QMenu, QAction, QVBoxLayout, QTreeWidget, QTreeWidgetItem, \
    QAbstractItemView, QColorDialog

from data.DataPool import DataPool
import numpy as np
import pyqtgraph as pg
import threading

__all__ = ['ChartWidget']

from icon.icon import Icon
from widgets.BaseUIEvents import BaseUIEvents
from widgets.SymbolWidget import SymbolWidget


class SignalSelectionDialog(QDialog):
    def __init__(self, database=None, parent=None):
        QDialog.__init__(self, parent)
        if database is None:
            database = []
        self.database = database
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.symbol_widget = SymbolWidget(database, parent, True)
        layout.addWidget(self.symbol_widget)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.set_selection)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.setModal(True)
        self.setWindowTitle('Signal Selection')
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        self.setWindowIcon(Icon.symbol())

    def set_selection(self):
        self.accept()
        self._selected = self.symbol_widget.getSelectedSignals()

    def get_selected_signals(self):
        return self._selected


@dataclass
class SignalChartProperties:
    name: str
    identifier: str
    # ref: typing.Any
    color: str
    ticks: List
    unit: str


class SignalListWidget(QTreeWidget):
    signal_added = Signal(SignalChartProperties)
    signal_deleted = Signal(str)
    signal_selected = Signal(str)
    signal_check_changed = Signal(str, bool)

    def __init__(self, parent=None):
        QTreeWidget.__init__(self, parent)
        self.data_pool = DataPool()
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.on_right_click)

        self.popMenu = QMenu(self)
        self.addSignalAction = QAction('&Add Signal', self, triggered=self.select_signal)
        self.popMenu.addAction(self.addSignalAction)
        self.setColorAction = QAction('&Set Color', self, triggered=self.set_signal_color)
        self.popMenu.addAction(self.setColorAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.signal_configs: typing.Dict[str, SignalChartProperties] = {}
        self.itemSelectionChanged.connect(self.signal_selection_changed)
        self.itemChanged.connect(self.item_changed)
        self.setColumnCount(2)
        self.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.header().setStretchLastSection(False)
        self.header().hide()
        # self.popMenu.addAction(QAction('test1', self))
        # self.popMenu.addSeparator()
        # self.popMenu.addAction(QAction('test2', self))

    def on_right_click(self, point):
        self.setColorAction.setEnabled(len(self.selectedItems()) == 1)
        self.popMenu.move(self.mapToGlobal(QtCore.QPoint(0, 0)) + point)
        self.popMenu.show()
        # self.setDragDropMode(QAbstractItemView.DragDrop)
        # self.setAcceptDrops(True)
        # self.popMenu.exec_(self.button.mapToGlobal(point))

    def set_widget_item_color(self, widget, color):
        def foregoundColor(bgColor: QColor):
            luminance = (0.299 * bgColor.red() + 0.587 * color.green() + 0.114 * color.blue()) / 255
            return QColor(Qt.GlobalColor.white) if luminance <= 0.5 else QColor(Qt.GlobalColor.black)

        if color.isValid():
            widget.setBackgroundColor(0, color)
            widget.setTextColor(0, foregoundColor(color))

    def set_signal_color(self):
        sel = self.selectedItems()[0]
        default_color = QColor(randint(0, 250), randint(0, 250), randint(0, 250))
        dialog = QColorDialog(self)
        dialog.setCurrentColor(default_color)
        color = dialog.getColor()
        sig = sel.data(0, Qt.UserRole).identifier
        self.signal_configs[sig].color = color.name()
        self.set_widget_item_color(sel, color)

    def add_single_item(self, sid, color):
        obj = self.data_pool.get_obj_by_sid(sid)
        if not obj:
            if ':' in sid:
                unit = 'ms'
                ticks = []
            else:
                return
        else:
            vt = self.data_pool.get_value_table_by_sid(sid)
            unit = obj.unit if obj.unit else '-'
            ticks = [] if not vt else [(k, v) for k, v in vt.items()]

        sig_name = sid.split('/')[-1]
        item = QTreeWidgetItem(self, [sig_name])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)
        # color = QColor(Qt.GlobalColor.blue)
        self.set_widget_item_color(item, color)
        self.signal_configs[sid] = SignalChartProperties(sig_name,
                                                         sid,
                                                         color.name(),
                                                         [ticks],
                                                         unit)
        item.setData(0, Qt.UserRole, self.signal_configs[sid])
        self.invisibleRootItem().addChild(item)
        self.signal_added.emit(self.signal_configs[sid])

    def add_item_by_sid(self, sids):
        for sid in sids:
            color = QColor(randint(0, 250), randint(0, 250), randint(0, 250))
            self.add_single_item(sid, color)

    def select_signal(self, config=None):
        if not config:
            dialog = SignalSelectionDialog(self.data_pool.databases, self)
            ret = dialog.exec_()
            if ret > 0:
                self.add_item_by_sid(dialog.get_selected_signals())
        else:
            if type(config) is str:
                sids = config.split('---')
                self.add_item_by_sid(sids)
            else:
                for k, v in config.items():
                    # todo: name may be changed / deleted
                    color = QColor()
                    color.setNamedColor(v.color)
                    self.add_single_item(k, color)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key_Delete:
            for i in self.selectedItems():
                ref = i.data(0, Qt.UserRole)
                self.takeTopLevelItem(self.indexOfTopLevelItem(i))
                if ref.identifier in self.signal_configs.keys():
                    self.signal_configs.pop(ref.identifier)
                    self.signal_deleted.emit(ref.identifier)
        else:
            super().keyPressEvent(event)

    def signal_selection_changed(self):
        if len(self.selectedItems()) == 1:
            sid = self.selectedItems()[0].data(0, Qt.UserRole).identifier
            self.signal_selected.emit(sid)

    @Slot(QTreeWidgetItem)
    def item_changed(self, item: QTreeWidgetItem):
        if item.data(0, Qt.UserRole):
            self.signal_check_changed.emit(item.data(0, Qt.UserRole).identifier, item.checkState(0))

    def show_value_column(self, show: bool):
        if show:
            self.showColumn(1)
        else:
            self.hideColumn(1)

    def set_sig_value(self, sid, value):
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            data = item.data(0, Qt.UserRole)
            if data and data.identifier == sid:
                cfg = self.signal_configs[sid]
                if cfg.ticks[0]:
                    k, v = next((p for p in cfg.ticks[0] if p[0] == value), (value, '--'))
                    item.setText(1, f'{str(int(k))}: {v}')
                else:
                    item.setText(1, f'{value:.3f}  {cfg.unit}')


class ChartWidget(BaseUIEvents, QWidget):
    new_message = Signal(object)

    def __init__(self, config=None, parent=None):
        QWidget.__init__(self, parent)
        self.data_pool = DataPool()
        self.signal_props = {}
        self.signal_viewbox: typing.Dict[str, pg.ViewBox] = {}
        self.signal_plot: typing.Dict[str, pg.PlotDataItem] = {}
        self.signal_miss_plot: typing.Dict[str, pg.ScatterPlotItem] = {}
        self.signal_axis: typing.Dict[str, pg.AxisItem] = {}

        self._update_time = datetime.now()
        self._move_view = True
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.proxy_single_line = None
        self._single_line_enabled = False
        self.region = pg.LinearRegionItem()
        self.region.setZValue(10)
        self._lock = threading.Lock()
        self._snap_shot = {}
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_chart)

        splitter = QtWidgets.QSplitter(self)
        layout = QtWidgets.QHBoxLayout()
        self.graph_view = pg.GraphicsView()
        self.plot_item = pg.PlotItem()
        self.graph_view.setCentralWidget(self.plot_item)
        self.plot_item.hideAxis('left')
        self.default_viewbox = self.plot_item.getViewBox()
        self.default_viewbox.sigResized.connect(self.update_viewbox)
        self.default_viewbox.setFocusPolicy(Qt.StrongFocus)
        self.default_viewbox.setXRange(0, 15)

        self.sig_info_widget = SignalListWidget(self)
        self.sig_info_widget.setMaximumWidth(550)
        self.sig_info_widget.setFrameStyle(QFrame.NoFrame)
        self.sig_info_widget.signal_added.connect(self.on_signal_added)
        self.sig_info_widget.signal_deleted.connect(self.on_signal_deleted)
        self.sig_info_widget.signal_check_changed.connect(self.on_signal_check_changed)
        self.sig_info_widget.show_value_column(False)

        splitter.addWidget(self.sig_info_widget)
        splitter.addWidget(self.graph_view)
        layout.addWidget(splitter)
        self.setLayout(layout)
        # self.new_message.connect(self.update_bus_message_internal)
        self.sig_info_widget.signal_selected.connect(self.signal_selected)
        if config:
            for sid in config.keys():
                self.data_pool.measure_signal(sid)
            self.sig_info_widget.select_signal(config)
        self.setAcceptDrops(True)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    @property
    def signal_config(self):
        return self.sig_info_widget.signal_configs

    def update_viewbox(self):
        for vb in list(self.signal_viewbox.values())[1:]:
            vb.setGeometry(self.default_viewbox.sceneBoundingRect())
            # vb.setXLink(self.default_viewbox)

    @Slot(str)
    def signal_selected(self, sid: str):
        for vb in self.signal_viewbox.values():
            vb.setEnabled(False)
        for axis in self.signal_axis.values():
            axis.setVisible(False)
        for s, pi in self.signal_plot.items():
            pi.setPen(pg.mkPen(color=self.signal_props[s].color, width=1))
        self.signal_plot[sid].setPen(pg.mkPen(color=self.signal_props[sid].color, width=3))
        self.signal_axis[sid].setVisible(True)
        self.signal_viewbox[sid].setEnabled(True)

    @Slot(SignalChartProperties)
    def on_signal_added(self, prop: SignalChartProperties):
        if prop.identifier in self.signal_props.keys():
            return
        self.data_pool.measure_signal(prop.identifier)
        self.signal_props[prop.identifier] = prop
        if len(self.signal_viewbox) == 0:
            axis = pg.AxisItem('right')
            axis.setLabel(f'{prop.name} [{prop.unit}]', color=prop.color)
            self.plot_item.setAxisItems({'right': axis})
            axis.show()
            self.signal_viewbox[prop.identifier] = self.default_viewbox
            # self.default_viewbox.disableAutoRange(pg.ViewBox.XYAxes)
            self.signal_axis[prop.identifier] = axis
            pi = pg.PlotDataItem(pen=pg.mkPen(color=prop.color, width=1), clipToView=True)
            self.signal_viewbox[prop.identifier].addItem(pi)
            self.signal_plot[prop.identifier] = pi
            self.signal_miss_plot[prop.identifier] = pg.ScatterPlotItem(pen=pg.mkPen(color=prop.color), size=8,
                                                                        symbol='o')
            self.signal_viewbox[prop.identifier].addItem(self.signal_miss_plot[prop.identifier])
        else:
            for vb in self.signal_viewbox.values():
                vb.setEnabled(False)
            for axis in self.signal_axis.values():
                axis.setVisible(False)
            axis = pg.AxisItem("right")
            axis.setLabel(f'{prop.name} [{prop.unit}]', color=prop.color)
            self.signal_axis[prop.identifier] = axis
            viewbox = pg.ViewBox()
            self.signal_viewbox[prop.identifier] = viewbox
            self.plot_item.layout.addItem(axis, 2, len(self.signal_axis) + 1)
            self.plot_item.scene().addItem(viewbox)
            axis.linkToView(viewbox)
            plot_item = pg.PlotDataItem(pen=pg.mkPen(color=prop.color, width=1), clipToView=True)
            self.signal_plot[prop.identifier] = plot_item
            self.signal_miss_plot[prop.identifier] = pg.ScatterPlotItem(pen=pg.mkPen(color=prop.color), size=8)
            viewbox.addItem(self.signal_miss_plot[prop.identifier])
            viewbox.addItem(plot_item)
            viewbox.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            # viewbox.disableAutoRange(pg.ViewBox.XYAxes)
        if prop.ticks[0]:
            self.signal_axis[prop.identifier].setTicks(prop.ticks)
        pause_action: QAction = self.signal_viewbox[prop.identifier].menu.addAction('Pause')
        pause_action.triggered.connect(self.toggle_move_view)
        self.signal_viewbox[prop.identifier].setXRange(0, 15)
        # self.signal_viewbox[prop.identifier].sigRangeChangedManually.connect(self.disable_move_view)

    def toggle_move_view(self):
        self._move_view = not self._move_view
        for vb in self.signal_viewbox.values():
            pause_action = next(a for a in vb.menu.actions() if a.text() in ['Pause', 'Continue'])
            if self._move_view:
                pause_action.setText('Pause')
            else:
                pause_action.setText('Continue')
        if not self._move_view:
            for sid in self.signal_viewbox.keys():
                self.signal_miss_plot[sid].clear()
                if not self.signal_viewbox[sid].linkedView(pg.ViewBox.XAxis):
                    self.signal_plot[sid].setSymbol('s')
                    self.signal_plot[sid].setSymbolPen(pg.mkPen(color=self.signal_props[sid].color, width=1))
                    self.signal_plot[sid].setSymbolSize(8)
                    self.signal_viewbox[sid].setXLink(self.default_viewbox)
            if not self._snap_shot:
                for sid in self.data_pool.signal_buffer.keys():
                    self._snap_shot[sid] = self.data_pool.signal_buffer[sid].copy()

    def disable_move_view(self):
        self._move_view = False
        for sid in self.signal_viewbox.keys():
            if not self.signal_viewbox[sid].linkedView(pg.ViewBox.XAxis):
                self.signal_plot[sid].setSymbol('s')
                self.signal_plot[sid].setSymbolSize(8)
                self.signal_viewbox[sid].setXLink(self.default_viewbox)
        if not self._snap_shot:
            for sid in self.signal_viewbox.keys():
                self._snap_shot[sid] = self.data_pool.signal_buffer[sid].copy()

    @Slot(str)
    def on_signal_deleted(self, sid):
        if self.signal_viewbox[sid] == self.default_viewbox:
            # move the last one to the default viewbox
            self.signal_viewbox[sid].removeItem(self.signal_plot[sid])
            self.plot_item.hideAxis('right')
            self.signal_props.pop(sid)
            self.signal_axis.pop(sid)
            self.signal_viewbox.pop(sid)
            self.signal_plot.pop(sid)
            self.signal_miss_plot.pop(sid)
            if len(self.signal_viewbox) >= 1:
                last_sid = list(self.signal_viewbox.keys())[-1]
                axis = self.signal_axis.pop(last_sid)
                vb = self.signal_viewbox.pop(last_sid)
                pi = self.signal_plot.pop(last_sid)
                mpi = self.signal_miss_plot.pop(last_sid)
                vb.removeItem(pi)
                vb.removeItem(mpi)
                self.plot_item.scene().removeItem(vb)
                axis.close()

                axis = pg.AxisItem('right')
                axis.setLabel(f'{self.signal_props[last_sid].name} [{self.signal_props[last_sid].unit}]',
                              color=self.signal_props[last_sid].color)
                self.plot_item.setAxisItems({'right': axis})
                self.signal_viewbox[last_sid] = self.default_viewbox
                self.signal_axis[last_sid] = axis
                pi = pg.PlotDataItem(pen=pg.mkPen(color=self.signal_props[last_sid].color, width=1), clipToView=True)
                self.signal_viewbox[last_sid].addItem(pi)
                self.signal_plot[last_sid] = pi
                self.signal_miss_plot[last_sid] = pg.ScatterPlotItem(
                    pen=pg.mkPen(color=self.signal_props[last_sid].color), size=8, symbol='o')
                self.signal_viewbox[last_sid].addItem(self.signal_miss_plot[last_sid])
                self.update_viewbox()
        else:
            axis = self.signal_axis.pop(sid)
            vb = self.signal_viewbox.pop(sid)
            pi = self.signal_plot.pop(sid)
            mpi = self.signal_miss_plot.pop(sid)
            vb.removeItem(pi)
            vb.removeItem(mpi)
            self.plot_item.scene().removeItem(vb)
            axis.close()
            self.signal_props.pop(sid)

    @Slot(str, bool)
    def on_signal_check_changed(self, sid, checked):
        if sid in self.signal_viewbox.keys():
            self.signal_viewbox[sid].setVisible(checked)

    def on_new_message(self, message):
        self.new_message.emit(message)

    def on_start_measurement(self):
        self.timer.start(100)
        self._move_view = True
        self.sig_info_widget.addSignalAction.setEnabled(False)
        for sid in self.signal_viewbox.keys():
            self.signal_plot[sid].clear()
            self.signal_miss_plot[sid].clear()

    def on_stop_measurement(self):
        self.timer.stop()
        self.sig_info_widget.addSignalAction.setEnabled(True)
        if self._move_view:
            self.toggle_move_view()

    def update_chart(self):
        self.update_bus_message_internal(None)

    @Slot(object)
    def update_bus_message_internal(self, message: typing.Union[object, None]):
        if not self.data_pool.start_time:
            return
        if (datetime.now() - self._update_time).total_seconds() < 0.1:
            return
        self._update_time = datetime.now()
        now = (datetime.now() - self.data_pool.start_time).total_seconds()
        for sid in self.signal_viewbox.keys():
            # if message is None and self._move_view:
            #     if now > 15:
            #         self.signal_viewbox[sid].setXRange(now - 15, now, update=False)
            if sid in self.data_pool.signal_buffer.keys():
                v = self.data_pool.signal_buffer[sid]
                if self._move_view:
                    x = v[:, 0]
                    diff = np.diff(x)
                    mask = diff > 1.0
                    mask1 = np.append(mask, False)
                    mask = np.insert(mask, 0, False)
                    self.signal_plot[sid].setSymbol(None)
                    mask = np.logical_or(mask, mask1)

                    self.signal_viewbox[sid].setXLink(None)
                    self.signal_plot[sid].setData(v)
                    if mask.any():
                        self.signal_miss_plot[sid].setData(x=x[mask], y=v[:, 1][mask])
                    self._snap_shot = {}
                if self._move_view and len(v) and v[-1, 0] > 10 and self.signal_viewbox[sid].isVisible():
                    self.signal_viewbox[sid].setXRange(now - 10, now, update=False)

    def enable_singleline(self):
        self.default_viewbox.addItem(self.vLine, ignoreBounds=True)
        self.sig_info_widget.show_value_column(True)

        # self.default_viewbox.addItem(self.hLine, ignoreBounds=True)
        def mouse_moved(evt):
            pos = evt[0]
            if self.default_viewbox.sceneBoundingRect().contains(pos):
                mouse_point = self.default_viewbox.mapSceneToView(pos)
                self.vLine.setPos(mouse_point.x())
                sid = next((k for k, v in self.signal_viewbox.items() if v.isEnabled()), None)
                if not sid:
                    sid = next(iter(self.signal_plot.keys()), None)
                    if not sid:
                        return
                if sid not in self._snap_shot.keys():
                    return
                for s in self.signal_plot.keys():
                    x = self._snap_shot[s][:, 0]
                    if not len(x):
                        continue
                    idx = np.searchsorted(x, mouse_point.x(), side="left")
                    if idx > 0 and (idx == len(x)):
                        idx -= 1
                    if s == sid:
                        self.vLine.setPos(x[idx])
                    self.sig_info_widget.set_sig_value(s, self._snap_shot[s][idx, 1])

        self.proxy_single_line = pg.SignalProxy(self.default_viewbox.scene().sigMouseMoved, rateLimit=60,
                                                slot=mouse_moved)

    def disable_singleline(self):
        self.default_viewbox.removeItem(self.vLine)
        # self.default_viewbox.removeItem(self.hLine)
        self.proxy_single_line.disconnect()
        self.sig_info_widget.show_value_column(False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Period:
            if not self._single_line_enabled:
                self.enable_singleline()
            else:
                self.disable_singleline()
            self._single_line_enabled = not self._single_line_enabled
        elif event.key() == Qt.Key_Comma:
            pass

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        if event.mimeData().hasText():
            if self.timer.isActive():
                event.ignore()
                return
            mime = event.mimeData()
            sids = mime.text().split('---')
            event.accept()
            self.sig_info_widget.add_item_by_sid(sids)
        else:
            event.ignore()
