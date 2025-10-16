# Python Artnet

Simple Artnet and Artsync packet broadcaster

## Usage

```python
import sys

from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from artnet.broadcaster import ArtnetBroadcaster

from pyside6helpers.slider import Slider


class ArtnetWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        target_ip = "192.168.20.12"
        universe_number = 0

        self._artnet = ArtnetBroadcaster(target_ip)
        self._artnet.add_universe(universe_number)

        QApplication.instance().setApplicationName(
            f"Artnet mini - {target_ip} universe {universe_number}"
        )

        self._sliders: list[Slider] = []
        layout = QHBoxLayout(self)

        for i in range(8):
            new_slider = Slider(
                name=f"CH {i + 1}",
                minimum=0, maximum=255,
                on_value_changed=lambda value, idx=i: self._on_slider_value_changed(idx, value),
                is_vertical=True
            )
            self._sliders.append(new_slider)
            layout.addWidget(new_slider)

    def _on_slider_value_changed(self, idx: int, value: int):
        self._artnet.universes[0].buffer[idx] = value
        
        # Sends DMX packets only, no Artsync
        self._artnet.send_data()
        
        # Sends DMX packets and an Artsync packet as well, useful with several universes
        self._artnet.send_data_synced()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setOrganizationName("Frangitron")

    w = ArtnetWidget()
    w.resize(300, 300)
    w.show()
    sys.exit(app.exec())
```

## Note

Packet generation borrowed from [StupidArtnet](https://github.com/cpvalente/stupidArtnet)
