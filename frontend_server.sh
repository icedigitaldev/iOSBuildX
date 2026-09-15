#!/bin/bash
# Installed in place of the engine's dartaotruntime. AOT compiles of the frontend
# server get the same Dart plugin registrant arguments that `flutter build` passes.
real="${BASH_SOURCE[0]}.real"
args=("$@")

if [[ "${1:-}" == */frontend_server_aot.dart.snapshot && " $* " == *" --aot "* ]]; then
  main="${args[-1]}"
  registrant="$(dirname "$(dirname "$main")")/.dart_tool/flutter_build/dart_plugin_registrant.dart"
  if [ -f "$registrant" ]; then
    uri="file://$(realpath "$registrant")"
    args=("${args[@]:0:${#args[@]}-1}"
          --target-os ios -Ddart.vm.profile=false
          --source "$uri" --source package:flutter/src/dart_plugin_registrant.dart
          "-Dflutter.dart_plugin_registrant=$uri"
          "$main")
  fi
fi

exec "$real" "${args[@]}"
