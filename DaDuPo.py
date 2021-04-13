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

import json
from functools import partial

from PySide2 import QtCore, QtWidgets, QtGui
from PySide2.QtCore import QSettings, Qt
from PySide2.QtWidgets import QMdiArea, QTabWidget, QMenu, QAction, QApplication

from data.Asap2Database import Asap2Parameter, Asap2Signal, ParameterType
from device.DeviceManager import DeviceManager
from icon.icon import Icon
from widgets.ArrayWidget import ArrayParameterWidget
from widgets.ChartWidget import ChartWidget
from data.DataPool import DataPool
from widgets.MeasurementConfigDialog import MeasurementConfigDialog
from widgets.ScalarWidget import ScalarParameterWidget, ScalarSignalWidget, ScalarBaseWidget
from widgets.SymbolWidget import SymbolWidget
import pyqtgraph as pg

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'b')


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.panels = []
        self.device_manager = DeviceManager()
        with open("project.json") as f:
            config = json.load(f)
            self.device_manager.load_devices(config['devices'])
        self._connected = False
        self._measurement_started = False
        self.data_pool = DataPool()

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setDocumentMode(True)
        self.setCentralWidget(self.tab_widget)
        self.setAcceptDrops(True)
        self.dropped_sids = ''

        self.register_shortcut()
        self.createActions()
        self.createMenus()
        self.createToolBars()
        self.createStatusBar()

        self.setWindowTitle("DaDuPo")
        self.setWindowIcon(Icon.app())

        settings = QSettings('demo.mcs', QSettings.IniFormat)
        self.settings = settings
        self.restoreGeometry(settings.value("geometry", bytes('', 'utf-8')))
        self.restoreState(settings.value("windowState", bytes('', 'utf-8')))
        self.data_pool.signal_config = settings.value('measurement_config', {})
        for i in range(settings.beginReadArray('pages')):
            settings.setArrayIndex(i)
            title = settings.value('title')
            self.create_page(title)
            for j in range(settings.beginReadArray('widgets')):
                settings.setArrayIndex(j)
                widget = settings.value('widget')
                if widget == SymbolWidget.__name__:
                    self.createSymbolPanel()
                elif widget == ChartWidget.__name__:
                    self.createGraphPanel(settings.value('config'))
                elif widget == ArrayParameterWidget.__name__:
                    self.createNonScalarParameterPanel(settings.value('config'))
                elif widget == ScalarParameterWidget.__name__:
                    self.createScalarParameterPanel(settings.value('config'))
                elif widget == ScalarSignalWidget.__name__:
                    self.createScalarSignalPanel(settings.value('config'))
                w = self.tab_widget.widget(i).currentSubWindow()
                w.restoreGeometry(settings.value("geometry", bytes('', 'utf-8')))
            settings.endArray()
        settings.endArray()

        if not self.tab_widget.count():
            self.create_page('Default')

        self.update_window_style()


    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            sids = event.mimeData().text().split('---')
            objs = [self.data_pool.get_obj_by_sid(s) for s in sids]
            types = set([type(o) for o in objs])
            if len(objs) >= 1 and len(types) == 1 and objs[0]:
                t = types.pop()
                if t == Asap2Parameter:
                    if len(set([o.parameter_type for o in objs])) == 1:
                        event.acceptProposedAction()
                elif t == Asap2Signal:
                    if len(set([o.count > 1 for o in objs])) == 1:
                        event.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        if event.mimeData().hasText():
            mime = event.mimeData()
            self.dropped_sids = mime.text()
            objs = [self.data_pool.get_obj_by_sid(s) for s in self.dropped_sids.split('---')]
            self.popMenu.clear()
            if type(objs[0]) == Asap2Parameter:
                if objs[0].parameter_type == ParameterType.ASCII:
                    self.popMenu.addAction(self.newDropScalarParameterAct)
                elif objs[0].parameter_type == ParameterType.VALUE:
                    self.popMenu.addAction(self.newDropScalarParameterAct)
                    self.popMenu.addAction(self.newDropScalarSignalAct)
                    self.popMenu.addAction(self.newDropChartAct)
                else:
                    self.popMenu.addAction(self.newDropNonScalarParameterAct)
            elif type(objs[0]) == Asap2Signal:
                self.popMenu.addAction(self.newDropScalarParameterAct)
                self.popMenu.addAction(self.newDropScalarSignalAct)
                self.popMenu.addAction(self.newDropChartAct)

            self.popMenu.move(self.mapToGlobal(QtCore.QPoint(0, 0)) + event.pos())
            self.popMenu.show()
            event.accept()

    def update_window_style(self):
        for i in range(self.tab_widget.count()):
            mdi: QMdiArea = self.tab_widget.widget(i)
            for w in mdi.subWindowList():
                keys = QtWidgets.QStyleFactory.keys()
                w.setStyle(QtWidgets.QStyleFactory.create('windowsvista'))

    def register_shortcut(self):
        import platform
        if platform.system() == 'Windows':
            exe_path = QApplication.applicationFilePath()
            exe_path = exe_path.replace("/", "\\")
            reg_type = QSettings('HKEY_CURRENT_USER\\SOFTWARE\\Classes\\.ddp', QSettings.NativeFormat)
            reg_icon = QSettings("HKEY_CURRENT_USER\\SOFTWARE\\Classes\\.ddp\\DefaultIcon", QSettings.NativeFormat)
            reg_shell = QSettings("HKEY_CURRENT_USER\\SOFTWARE\\Classes\\.ddp\\Shell\\Open\\Command", QSettings.NativeFormat)
            # . means default value, you can also use the "Default" string
            if "" != reg_type.value("."):
                reg_type.setValue(".", "")

            # 0 使用当前程序内置图标
            val = exe_path + ",0"
            if val != reg_icon.value("."):
                reg_icon.setValue(".", val)

            val = exe_path + " \"%1\""
            if val != reg_shell.value("."):
                reg_shell.setValue(".", val)

    def closeEvent(self, event):
        if self._measurement_started:
            self.stop_measurement()
        if self._connected:
            self.disconnect_device()
        self.device_manager.close()
        settings = self.settings
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("measurement_config", self.data_pool.signal_config)
        settings.beginWriteArray('pages')
        for i in range(self.tab_widget.count()):
            settings.setArrayIndex(i)
            mdi: QMdiArea = self.tab_widget.widget(i)
            settings.setValue('title', self.tab_widget.tabText(i))
            wins = mdi.subWindowList()
            settings.beginWriteArray('widgets')
            for j, win in enumerate(wins):
                settings.setArrayIndex(j)
                w = win.widget()
                settings.setValue('geometry', win.saveGeometry())
                settings.setValue('widget', type(w).__name__)
                if type(w) is ChartWidget:
                    settings.setValue('config', w.signal_config)
                elif issubclass(type(w), ScalarBaseWidget):
                    settings.setValue('config', w.get_scalars())
                elif type(w) is ArrayParameterWidget:
                    settings.setValue('config', w.get_config())
            settings.endArray()
            # settings.setValue('geometry', w.saveGeometry())
            # settings.beginGroup('widgets')
            # settings.endGroup()
        settings.endArray()
        super(MainWindow, self).closeEvent(event)

    def about(self):
        QtWidgets.QMessageBox.about(self, "About DaDuPo",
                                    "Developed by Jun.")

    # noinspection PyArgumentList,PyAttributeOutsideInit
    def createActions(self):
        self.newPageAct = QAction('&Page', self, triggered=self.create_page)
        self.newChartAct = QAction('&Graph Panel', self, triggered=self.createGraphPanel)
        self.newSymbolSelAct = QAction('&Symbol Panel', self, triggered=self.createSymbolPanel)
        self.newScalarParameterAct = QAction('&Scalar Parameter Panel', self,
                                             triggered=self.createScalarParameterPanel)
        self.newScalarSignalAct = QAction('&Scalar Signal Panel', self,
                                          triggered=self.createScalarSignalPanel)
        self.configMeasurementAct = QAction('&Config Measurement', self, triggered=self.config_measurement)
        self.configMeasurementAct.setEnabled(False)

        self.connectAct = QAction(Icon.connect(), "&Connect", self,
                                  triggered=self.connect_device)
        self.disconnectAct = QAction(Icon.disconnect(), "&Disconnect", self,
                                     triggered=self.disconnect_device)
        self.disconnectAct.setEnabled(False)
        self.startMeasurementAct = QAction(QtGui.QIcon('icon/play.svg'), "&Start Measurement", self,
                                           triggered=self.start_measurement)
        self.startMeasurementAct.setEnabled(False)
        self.stopMeasurementAct = QAction(QtGui.QIcon('icon/stop.svg'), "&Stop Measurement", self,
                                          triggered=self.stop_measurement)
        self.stopMeasurementAct.setEnabled(False)

        self.quitAct = QAction("&Quit", self, shortcut="Ctrl+Q", triggered=self.close)

        self.aboutAct = QAction("&About", self, triggered=self.about)

        self.newDropChartAct = QAction('&Graph Panel', self,
                                       triggered=lambda: self.createGraphPanel(self.dropped_sids))
        self.newDropScalarParameterAct = QAction('&Scalar Parameter Panel', self,
                                                 triggered=lambda: self.createScalarParameterPanel(self.dropped_sids))
        self.newDropNonScalarParameterAct = QAction('&Curve/Map Panel', self,
                                                 triggered=lambda: self.createNonScalarParameterPanel(self.dropped_sids))
        self.newDropScalarSignalAct = QAction('&Scalar Signal Panel', self,
                                              triggered=lambda: self.createScalarSignalPanel(self.dropped_sids))

    def createMenus(self):
        self.fileMenu = self.menuBar().addMenu("&File")
        self.fileMenu.addAction(self.quitAct)

        self.editMenu = self.menuBar().addMenu("&Edit")
        self.editMenu.addAction(self.configMeasurementAct)

        self.viewMenu = self.menuBar().addMenu("&View")
        self.view_new_submenu = self.viewMenu.addMenu('New')
        self.view_new_submenu.addAction(self.newPageAct)
        self.view_new_submenu.addAction(self.newChartAct)
        self.view_new_submenu.addAction(self.newSymbolSelAct)
        self.view_new_submenu.addAction(self.newScalarParameterAct)
        self.view_new_submenu.addAction(self.newScalarSignalAct)
        self.menuBar().addSeparator()

        self.helpMenu = self.menuBar().addMenu("&Help")
        self.helpMenu.addAction(self.aboutAct)

        self.popMenu = QMenu(self)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        # self.customContextMenuRequested.connect(self.on_right_click)

    def on_right_click(self, point):
        self.popMenu.move(self.mapToGlobal(QtCore.QPoint(0, 0)) + point)
        self.popMenu.show()

    def createToolBars(self):
        self.device_bar = self.addToolBar("Device")
        self.device_bar.addAction(self.connectAct)
        self.device_bar.addAction(self.disconnectAct)
        self.device_bar.addSeparator()
        self.device_bar.addAction(self.startMeasurementAct)
        self.device_bar.addAction(self.stopMeasurementAct)

    def createStatusBar(self):
        self.statusBar().showMessage("Ready")

    def create_page(self, title=None):
        if not title:
            text, ok = QtWidgets.QInputDialog.getText(self, "New Page",
                                                      "Page Title:", QtWidgets.QLineEdit.Normal,
                                                      f'Page {self.tab_widget.count() + 1}')
        else:
            text, ok = (title, 1)
        if ok and text != '':
            mdiArea = QMdiArea()
            mdiArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            mdiArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            tab = self.tab_widget.addTab(mdiArea, text)
            self.tab_widget.setCurrentIndex(tab)
        # if self.tab_widget.count():

    def createGraphPanel(self, config=None):
        chart_widget = ChartWidget(config, self)
        chart_widget.setWindowTitle('Graph')
        self.tab_widget.currentWidget().addSubWindow(chart_widget)
        chart_widget.show()
        self.tab_widget.currentWidget().currentSubWindow().setWindowIcon(Icon.chart())
        self.update_window_style()
        self.panels.append(chart_widget)
        chart_widget.closed.connect(partial(self.panels.remove, chart_widget))

    def createSymbolPanel(self):
        widget = SymbolWidget(self.data_pool.databases, self)
        widget.setWindowTitle('Select Symbol')
        page: QMdiArea = self.tab_widget.currentWidget()
        win = page.addSubWindow(widget)
        page.setActiveSubWindow(win)
        win.setWindowIcon(Icon.symbol())
        widget.show()
        widget.treeWidget.mouse_clicked.connect(self.create_panel_for_sig)
        self.update_window_style()
        self.panels.append(widget)
        widget.closed.connect(partial(self.panels.remove, widget))

    def createScalarParameterPanel(self, config=None):
        widget = ScalarParameterWidget(config, self)
        widget.setWindowTitle('Scalar Parameter')
        self.tab_widget.currentWidget().addSubWindow(widget)
        widget.show()
        self.tab_widget.currentWidget().currentSubWindow().setWindowIcon(Icon.scalar_parameter())
        self.update_window_style()
        self.panels.append(widget)
        widget.closed.connect(partial(self.panels.remove, widget))

    def createNonScalarParameterPanel(self, config=None):
        widget = ArrayParameterWidget(config, self)
        self.tab_widget.currentWidget().addSubWindow(widget)
        widget.show()
        self.tab_widget.currentWidget().currentSubWindow().setWindowIcon(Icon.array_parameter())
        self.update_window_style()
        self.panels.append(widget)
        widget.closed.connect(partial(self.panels.remove, widget))

    def createScalarSignalPanel(self, config=None):
        widget = ScalarSignalWidget(config, self)
        widget.setWindowTitle('Scalar Signal')
        self.tab_widget.currentWidget().addSubWindow(widget)
        widget.show()
        self.tab_widget.currentWidget().currentSubWindow().setWindowIcon(Icon.scalar_signal())
        self.update_window_style()
        self.panels.append(widget)
        widget.closed.connect(partial(self.panels.remove, widget))

    def create_panel_for_sig(self, sig):
        if not sig:
            return
        obj = self.data_pool.get_obj_by_sid(sig)
        if type(obj) is Asap2Parameter:
            if obj.parameter_type in [ParameterType.VALUE, ParameterType.ASCII]:
                self.createScalarParameterPanel(sig)
            else:
                self.createNonScalarParameterPanel(sig)
        elif type(obj) is Asap2Signal:
            self.createScalarSignalPanel(sig)

    def config_measurement(self):
        dialog = MeasurementConfigDialog(self)
        dialog.exec_()

    def connect_device(self):
        try:
            self.device_manager.connect()
        except Exception as e:
            QtWidgets.QMessageBox.information(self, "Error", 'device connect failed! \n\n' + str(e))
            return
        self.connectAct.setEnabled(False)
        self.disconnectAct.setEnabled(True)
        self.startMeasurementAct.setEnabled(True)
        self.stopMeasurementAct.setEnabled(False)
        for p in self.panels:
            p.on_device_connected()

        self.configMeasurementAct.setEnabled(True)
        self._connected = True

    def disconnect_device(self):
        try:
            self.device_manager.disconnect()
        except Exception as e:
            QtWidgets.QMessageBox.information(self, "Error", 'device disconnect failed! \n\n' + str(e))
        self.connectAct.setEnabled(True)
        self.disconnectAct.setEnabled(False)
        self.startMeasurementAct.setEnabled(False)
        self.stopMeasurementAct.setEnabled(False)
        for p in self.panels:
            p.on_device_disconnected()
        self.configMeasurementAct.setEnabled(False)
        self._connected = False

    def start_measurement(self):
        try:
            self.device_manager.start_measurement()
        except Exception as e:
            QtWidgets.QMessageBox.information(self, "Error", 'start measurement failed! \n\n' + str(e))
            return
        self.data_pool.on_start_measurement()
        self.connectAct.setEnabled(False)
        self.disconnectAct.setEnabled(False)
        self.startMeasurementAct.setEnabled(False)
        self.stopMeasurementAct.setEnabled(True)
        for p in self.panels:
            p.on_start_measurement()
        self._measurement_started = True

    def stop_measurement(self):
        try:
            self.device_manager.stop_measurement()
        except Exception as e:
            QtWidgets.QMessageBox.information(self, "Error", 'stop measurement failed! \n\n' + str(e))
        self.connectAct.setEnabled(False)
        self.disconnectAct.setEnabled(True)
        self.startMeasurementAct.setEnabled(True)
        self.stopMeasurementAct.setEnabled(False)
        for p in self.panels:
            p.on_stop_measurement()
        self._measurement_started = False


QSS = """
QMdiSubWindow:title{
    background: lightgray;
}
"""

if __name__ == '__main__':
    import sys

    app = QtWidgets.QApplication(sys.argv)
    mainWin = MainWindow()
    # mainWin.showMaximized()
    mainWin.show()
    sys.exit(app.exec_())
