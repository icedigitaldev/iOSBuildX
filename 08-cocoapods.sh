#!/bin/bash
# Instala CocoaPods (la gema completa, no solo cocoapods-core) para usar su
# Resolver/Analyzer como fuente de verdad de los flags de cada pod.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive

command -v ruby >/dev/null || {
  apt-get update -qq
  apt-get install -y -qq ruby-full ruby-dev build-essential libffi-dev || exit 1
}

gem list -i cocoapods >/dev/null 2>&1 || \
  gem install --no-document cocoapods || exit 1

pod --version --allow-root
ruby -e 'require "cocoapods"; puts "cocoapods #{Pod::VERSION} ok"'
