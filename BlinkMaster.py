import sys
import os
import math
import time
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QSlider, QPushButton, QColorDialog, QSystemTrayIcon, QMenu,
                             QGraphicsOpacityEffect, QFormLayout)
from PyQt6.QtGui import QIcon, QAction, QColor
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QThread, pyqtSlot, QSettings


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# OverlayWindow 和 Worker 类无需改动
class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self);
        layout.setContentsMargins(0, 0, 0, 0)
        self.color_block = QWidget(self);
        layout.addWidget(self.color_block)
        self.opacity_effect = QGraphicsOpacityEffect(self.color_block);
        self.color_block.setGraphicsEffect(self.opacity_effect)
        self.set_color(QColor("gray"));
        self.set_opacity(0.0)

    def set_color(self, color): self.color_block.setStyleSheet(f"background-color: {color.name()};")

    def set_opacity(self, opacity): self.opacity_effect.setOpacity(opacity)


class Worker(QObject):
    pulse_signal = pyqtSignal()

    def __init__(self):
        super().__init__();
        self._is_running = False;
        self.interval = 10

    @pyqtSlot()
    def run(self):
        self._is_running = True
        while self._is_running:
            for i in range(self.interval * 10):
                if not self._is_running: return
                QThread.msleep(100)
            if self._is_running: self.pulse_signal.emit()

    def stop(self):
        self._is_running = False


# ===============================================================
# 3. 【已增加设置记忆功能】主控制窗口 (MainApp)
# ===============================================================
class MainApp(QWidget):
    def __init__(self):
        super().__init__()

        # 【关键改动】初始化 QSettings
        # "MyCompany"和"BlinkMaster"可以自定义，它们决定了设置在注册表或配置文件中的位置
        self.settings_manager = QSettings("BlinkMasterApp", "BlinkMaster")

        self.is_active = False
        # 【关键改动】加载设置，如果失败则使用默认值
        self.load_settings()

        self.overlay = OverlayWindow()
        self.q_thread = QThread()
        self.worker = Worker()
        self.worker.moveToThread(self.q_thread)
        self.q_thread.started.connect(self.worker.run)
        self.worker.pulse_signal.connect(self.run_pulse_animation)
        self.q_thread.finished.connect(self.on_thread_finished)
        self.init_ui()
        self.create_tray_icon()
        self.q_thread.start()

    # 【关键改动】新增加载和保存设置的方法
    def load_settings(self):
        """程序启动时加载设置"""
        self.settings = {}
        # value() 方法的第二个参数是默认值，第三个是类型
        self.settings["interval"] = self.settings_manager.value("interval", 10, type=int)
        self.settings["opacity"] = self.settings_manager.value("opacity", 0.20, type=float)
        # QColor 可以被 QSettings 直接处理
        self.settings["color"] = self.settings_manager.value("color", QColor("gray"), type=QColor)
        self.settings["duration"] = 1.0  # 动画时长我们暂时不开放给用户调节

    def save_settings(self):
        """当设置改变时保存"""
        self.settings_manager.setValue("interval", self.settings["interval"])
        self.settings_manager.setValue("opacity", self.settings["opacity"])
        self.settings_manager.setValue("color", self.settings["color"])

    def init_ui(self):
        self.setWindowTitle("Blink Master - 护眼大师")
        self.setWindowIcon(QIcon(resource_path("icon.png")))
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20);
        main_layout.setSpacing(18)
        title_label = QLabel("护眼大师设置");
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;");
        main_layout.addWidget(title_label)
        form_layout = QFormLayout();
        form_layout.setSpacing(10)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        # 【关键改动】UI控件的初始值现在来自加载的设置
        self.interval_slider = self.create_slider(2, 30, self.settings["interval"], self.on_interval_change)
        self.interval_label = QLabel(f"{self.settings['interval']} 秒")
        interval_hbox = QHBoxLayout();
        interval_hbox.addWidget(self.interval_slider);
        interval_hbox.addWidget(self.interval_label)
        form_layout.addRow("扰动间隔:", interval_hbox)

        self.opacity_slider = self.create_slider(5, 50, int(self.settings["opacity"] * 100), self.on_opacity_change)
        self.opacity_label = QLabel(f"{int(self.settings['opacity'] * 100)}%")
        opacity_hbox = QHBoxLayout();
        opacity_hbox.addWidget(self.opacity_slider);
        opacity_hbox.addWidget(self.opacity_label)
        form_layout.addRow("扰动强度:", opacity_hbox)

        self.color_button = QPushButton("选择颜色");
        self.color_button.clicked.connect(self.choose_color)
        self.color_preview = QLabel();
        self.update_color_preview()
        color_hbox = QHBoxLayout();
        color_hbox.addWidget(self.color_button);
        color_hbox.addWidget(self.color_preview);
        color_hbox.addStretch()
        form_layout.addRow("扰动颜色:", color_hbox)
        main_layout.addLayout(form_layout)
        main_layout.addStretch(1)
        self.toggle_button = QPushButton("启动护眼模式")
        self.toggle_button.setStyleSheet("font-size: 16px; padding: 10px;");
        self.toggle_button.setCheckable(True)
        self.toggle_button.clicked.connect(self.toggle_service)
        main_layout.addWidget(self.toggle_button)

    def on_interval_change(self, value):
        self.settings["interval"] = value;
        self.interval_label.setText(f"{value} 秒")
        self.worker.interval = value
        self.save_settings()  # 【关键改动】保存设置

    def on_opacity_change(self, value):
        self.settings["opacity"] = value / 100.0;
        self.opacity_label.setText(f"{value}%")
        self.save_settings()  # 【关键改动】保存设置

    def choose_color(self):
        color = QColorDialog.getColor(self.settings["color"], self, "选择颜色")
        if color.isValid():
            self.settings["color"] = color;
            self.update_color_preview()
            self.overlay.set_color(color)
            self.save_settings()  # 【关键改动】保存设置

    # 其他方法无需改动
    def create_slider(self, min_val, max_val, current_val, callback):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val);
        slider.setValue(current_val);
        slider.valueChanged.connect(callback)
        return slider

    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(QIcon(resource_path("icon.png")), self)
        self.tray_icon.setToolTip("Blink Master")
        tray_menu = QMenu();
        show_action = QAction("显示主窗口", self, triggered=self.show)
        quit_action = QAction("退出", self, triggered=self.quit_app)
        tray_menu.addAction(show_action);
        tray_menu.addSeparator();
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu);
        self.tray_icon.show()

    def update_color_preview(self):
        self.color_preview.setFixedSize(24, 24);
        self.color_preview.setStyleSheet(f"border: 1px solid grey; background-color: {self.settings['color'].name()};")

    def toggle_service(self, checked):
        if checked:
            self.start_service(); self.toggle_button.setText("停止护眼模式")
        else:
            self.stop_service(); self.toggle_button.setText("启动护眼模式")

    def start_service(self):
        self.is_active = True;
        self.worker.interval = self.settings["interval"];
        self.worker._is_running = True
        self.overlay.set_color(self.settings["color"]);
        QTimer.singleShot(0, self.worker.run)
        self.overlay.setGeometry(QApplication.primaryScreen().geometry());
        self.overlay.show()

    def stop_service(self):
        self.is_active = False;
        self.worker.stop();
        self.overlay.hide()

    def run_pulse_animation(self):
        if not self.is_active: return
        start_time = time.time();
        duration = self.settings["duration"];
        max_opacity = self.settings["opacity"]

        def update_frame():
            elapsed = time.time() - start_time
            if elapsed < duration and self.is_active:
                progress = elapsed / duration;
                current_opacity = max_opacity * math.sin(progress * math.pi)
                self.overlay.set_opacity(current_opacity);
                QTimer.singleShot(15, update_frame)
            elif self.is_active:
                self.overlay.set_opacity(0)

        update_frame()

    def on_thread_finished(self):
        pass

    def safe_shutdown_worker(self):
        if self.q_thread.isRunning():
            self.stop_service();
            self.q_thread.quit()
            if not self.q_thread.wait(3000): self.q_thread.terminate(); self.q_thread.wait()

    def quit_app(self):
        self.safe_shutdown_worker();
        self.tray_icon.hide();
        QApplication.instance().quit()

    def closeEvent(self, event):
        self.hide();
        self.tray_icon.showMessage("Blink Master", "程序仍在后台运行...", QSystemTrayIcon.MessageIcon.Information, 2000)
        event.ignore()


# 程序入口
if __name__ == '__main__':
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    main_window = MainApp()
    main_window.show()
    sys.exit(app.exec())