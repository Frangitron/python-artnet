import sys
from PySide6.QtCore import QSettings

from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget, QVBoxLayout, QLabel, QLineEdit, QSpinBox

from pythonartnet.broadcaster import ArtnetBroadcaster

from pyside6helpers import css
from pyside6helpers.main_window import MainWindow
from pyside6helpers.slider import Slider


class ArtnetWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        settings = QSettings()
        self._target_ip = settings.value("target_ip", "192.168.20.100")
        self._universe_number = int(settings.value("universe_number", 1))
        self._start_channel = int(settings.value("start_channel", 1))

        self._setup_artnet()

        # Layouts
        main_layout = QVBoxLayout(self)
        settings_layout = QHBoxLayout()
        self._sliders_layout = QHBoxLayout()

        # Target IP Widget
        settings_layout.addWidget(QLabel("Target IP:"))
        self._ip_edit = QLineEdit(self._target_ip)
        self._ip_edit.editingFinished.connect(self._on_settings_changed)
        settings_layout.addWidget(self._ip_edit)

        # Universe Widget
        settings_layout.addWidget(QLabel("Universe:"))
        self._universe_spin = QSpinBox()
        self._universe_spin.setRange(0, 32767)
        self._universe_spin.setValue(self._universe_number)
        self._universe_spin.valueChanged.connect(self._on_settings_changed)
        settings_layout.addWidget(self._universe_spin)

        # Start Channel Widget
        settings_layout.addWidget(QLabel("First Channel:"))
        self._channel_spin = QSpinBox()
        self._channel_spin.setRange(1, 512)
        self._channel_spin.setValue(self._start_channel)
        self._channel_spin.valueChanged.connect(self._on_settings_changed)
        settings_layout.addWidget(self._channel_spin)

        main_layout.addLayout(settings_layout)
        main_layout.addLayout(self._sliders_layout)

        self._sliders: list[Slider] = []
        self._rebuild_sliders()

    def _setup_artnet(self):
        self._artnet = ArtnetBroadcaster(self._target_ip)
        self._artnet.add_universe(self._universe_number)

    def _on_settings_changed(self):
        self._target_ip = self._ip_edit.text()
        self._universe_number = self._universe_spin.value()
        self._start_channel = self._channel_spin.value()

        settings = QSettings()
        settings.setValue("target_ip", self._target_ip)
        settings.setValue("universe_number", self._universe_number)
        settings.setValue("start_channel", self._start_channel)

        self._setup_artnet()
        self._rebuild_sliders()

    def _rebuild_sliders(self):
        # Clear existing sliders
        for slider in self._sliders:
            self._sliders_layout.removeWidget(slider)
            slider.deleteLater()
        self._sliders.clear()

        # Create new sliders based on start_channel
        for i in range(8):
            ch_idx = i + self._start_channel - 1
            if ch_idx > 511: break

            new_slider = Slider(
                name=f"CH {ch_idx + 1}",
                minimum=0, maximum=255,
                on_value_changed=lambda value, idx=ch_idx: self._on_slider_value_changed(idx, value),
                is_vertical=True
            )
            self._sliders.append(new_slider)
            self._sliders_layout.addWidget(new_slider)

    def _on_slider_value_changed(self, idx: int, value: int):
        self._artnet.universes[self._universe_number].buffer[idx] = value

        # Sends DMX packets only, no Artsync
        #self._artnet.send_data()

        # Sends DMX packets and an Artsync packet as well, useful with several universes
        self._artnet.send_data_synced()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setOrganizationName("Frangitron")
    app.setApplicationName(f"Artnet mini")

    css.load_onto(app, "dark-touch.qss")

    mw = MainWindow()
    mw.setCentralWidget(ArtnetWidget())
    mw.show()
    sys.exit(app.exec())
