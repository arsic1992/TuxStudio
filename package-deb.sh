#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
version=0.10.2.1
arch=$(dpkg --print-architecture)
exe=dist/TuxStudio/TuxStudio
[[ -x "$exe" ]] || { echo 'Run bash build-linux.sh first.' >&2; exit 1; }
[[ $("$exe" --version) == "Tux Studio $version (development preview)" ]]
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT
install -d "$root/DEBIAN" "$root/opt/tux-studio" "$root/usr/bin" "$root/usr/share/applications" "$root/usr/share/mime/packages" "$root/usr/share/icons/hicolor/scalable/apps" "$root/usr/share/doc/tux-studio"
cp -a dist/TuxStudio/. "$root/opt/tux-studio/"
ln -s /opt/tux-studio/TuxStudio "$root/usr/bin/tux-studio"
install -m644 tux-studio.desktop "$root/usr/share/applications/"
install -m644 tux.xml "$root/usr/share/mime/packages/"
install -m644 tux-studio.svg "$root/usr/share/icons/hicolor/scalable/apps/"
install -m644 README.md "$root/usr/share/doc/tux-studio/"
cat > "$root/DEBIAN/control" <<CONTROL
Package: tux-studio
Version: $version
Architecture: $arch
Maintainer: Tux Studio Project
Section: devel
Priority: optional
Depends: libc6, libgl1, libegl1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, shared-mime-info, desktop-file-utils
Description: KDE-inspired development environment for TUX
 Development preview with editor, diagnostics and integrated runtime.
CONTROL
mkdir -p packages
out="packages/TuxStudio.deb"
tmp=$(mktemp -d packages/.build.XXXXXX)
trap 'rm -rf -- "$root" "$tmp"' EXIT
# Use gzip for compatibility with older APT/dpkg versions.
dpkg-deb -Zgzip --root-owner-group --build "$root" "$tmp/package.deb"
dpkg-deb --info "$tmp/package.deb"
dpkg-deb --contents "$tmp/package.deb" > "$tmp/contents.txt"
dpkg-deb --fsys-tarfile "$tmp/package.deb" | tar -tf - > /dev/null
mv -f -- "$tmp/package.deb" "$out"
echo "Validated package: $out"
