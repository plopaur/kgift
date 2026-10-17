# KGift 🎁

A small Qt/KDE program: an isometric gift box that opens with a click.
The lid flies off, confetti rains down and a picture pops out –
by default `gp.jpg` from the program folder (if it is missing, a heart is drawn instead).

<p align="center"><img src="docs/screenshot.png" alt="KGift screenshot: the opened gift box with confetti and the picture popping out" width="420"></p>

This project is a fork of [KGift on SourceForge](https://sourceforge.net/projects/kgift/) by [hiasl](https://sourceforge.net/u/hiasl/profile/).

## Running

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python kgift.py                  # with gp.jpg
.venv/bin/python kgift.py /path/image.jpg  # with your own image
```

On KDE/Linux you can also use your distribution's package instead of a venv
(e.g. `python3-pyside6` or `pyside6`).

## Controls

- **Left click / Space** – open the box, click again to close it
- **Drag an image into the window** – new picture for the surprise
- **Right click** – choose image, close box, quit
- **Esc / Q** – quit

## Adding it to the KDE menu

```bash
install -Dm755 kgift.py ~/.local/bin/kgift
install -Dm644 gp.jpg ~/.local/share/kgift/gp.jpg
install -Dm644 kgift.desktop ~/.local/share/applications/kgift.desktop
```

## License

MIT – see [LICENSE](LICENSE).
