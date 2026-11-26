# Tux Studio 0.10.2.1 development preview
On Debian-based Linux distributions (including Debian, Ubuntu, Linux Mint, and other compatible .deb-based systems), extract this kit and open a terminal in the extracted directory.
Run `bash build-linux.sh` then `bash package-deb.sh`. Internet access is needed for the build. Install with `sudo apt install ./packages/TuxStudio.deb`.
Launch from the application menu or `tux-studio`. Remove with `sudo apt remove tux-studio`. User settings are retained. File associations are registered as a supported handler, not forced as default.
Build on the target distribution or a compatible older baseline. The installer targets .deb-based Linux distributions; compatibility depends on CPU architecture, system libraries and available dependencies. Linux Mint has been tested by the project user; other distributions have not yet been verified. This is a development preview, not a sandbox for untrusted code. Third-party dependency license notices must be audited before public redistribution.

## Source and architecture

TUX is an interpreted language with its own lexer, parser, semantic analyzer and runtime. Tux Studio is its graphical development environment. The complete current implementation is in [TuxStudio.py](TuxStudio.py). See [the source map](SOURCE_MAP.md) for navigation and [the language reference](docs/index.html) for syntax and implementation status.

```tux
func double(n as int) as int with alias("twice") => n * 2
5 |> twice() |> display()
```

Expected output: `10`.

## Build from source

On Linux Mint or a compatible Debian-based system, install the build prerequisites if needed:

```bash
sudo apt install python3 python3-venv python3-pip dpkg-dev
bash build-linux.sh
bash package-deb.sh
sudo apt install ./packages/TuxStudio.deb
```

To run the source directly:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python TuxStudio.py
```

Run the headless function alias regression tests with `python3 alias-tests.py`. The executable smoke test runs automatically during the build. Dependency ranges are not locked, so builds are not guaranteed to be byte-for-byte reproducible.

## Publish documentation

Configure GitHub Pages to publish from the `docs/` directory on the default branch. Copy the locally built `packages/TuxStudio.deb` to `docs/TuxStudio.deb` to enable the existing download link. Add screenshots named `tux-studio-editor.png` and `tux-studio-console.png` in `docs/images/`. These binary assets are not supplied in this source archive.

## License and redistribution

A project license has not yet been selected. Public source visibility does not itself grant permission to modify or redistribute the project. See [LICENSING.md](LICENSING.md) before publishing a release. The bundled dependency licenses and notices require a separate audit.
