#!/bin/sh
set -e
cd "$(dirname "$0")/.."
FLAGS="-std=c11 -O2 -Wall -Wextra -Werror -shared"

clang $FLAGS -fvisibility=hidden -arch arm64 -arch x86_64 -mmacosx-version-min=11.0 \
    -install_name @rpath/libexciton_audio.dylib -o libs/libexciton_audio.dylib native/exciton_audio.c

out=$(mktemp -d)
for target in x86_64-windows-gnu:exciton_audio_x64.dll aarch64-windows-gnu:exciton_audio_arm64.dll \
    x86_64-linux-gnu.2.17:libexciton_audio_x86_64.so aarch64-linux-gnu.2.17:libexciton_audio_aarch64.so; do
    zig cc $FLAGS -fPIC -fvisibility=hidden -s -target "${target%%:*}" -o "$out/${target#*:}" native/exciton_audio.c
    cp "$out/${target#*:}" libs/
done
rm -rf "$out"
