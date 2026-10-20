# KGift 🎁

A small Qt/KDE program, with a native Android port: an isometric gift box that opens with a click.
The lid flies off, confetti rains down and a picture pops out –
by default `picture.jpg` from the program folder (if it is missing, a birthday cake is drawn instead).

<p align="center"><img src="docs/screenshot.png" alt="KGift screenshot: the opened gift box with confetti and a birthday cake popping out" width="420"></p>

This project is a fork of [KGift on SourceForge](https://sourceforge.net/projects/kgift/) by [hiasl](https://sourceforge.net/u/hiasl/profile/).

## Running

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python kgift.py                  # picture.jpg next to the script, else the cake
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
install -Dm644 picture.jpg ~/.local/share/kgift/picture.jpg  # optional, your own picture
install -Dm644 kgift.desktop ~/.local/share/applications/kgift.desktop
```

## Android

`android/` contains a native Android port (Kotlin, `android.graphics.Canvas`) of the same
animation – tap to open the box, tap again to close it, Back quits.
Open the folder in Android Studio, or build from the command line:

```bash
cd android
./gradlew installDebug    # build and install on a connected phone
```

Gradle needs JDK 17–21; Android Studio's own JDK is newer, so point `JAVA_HOME`
at a JDK 21 when building from the terminal.

A birthday cake pops out by default; to show your own picture instead, put it at `android/app/src/main/assets/picture.jpg`.

### Keeping both ports in sync

`GiftView.kt` mirrors `kgift.py` function by function. `tools/check_parity.py` pairs the
functions by name and compares their numeric and colour literals; known, intentional
differences live in `tools/parity-baseline.json`. Enable the pre-commit hook once per clone:

```bash
git config core.hooksPath .githooks
```

If a difference is intentional, accept it with `python3 tools/check_parity.py --update`
and commit the updated baseline.

## License

MIT – see [LICENSE](LICENSE).
