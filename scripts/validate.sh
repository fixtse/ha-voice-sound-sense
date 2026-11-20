#!/usr/bin/env bash
# Run on your build host. No device access or credentials required.
set -euo pipefail
cd "$(dirname "$0")/.."
image=ghcr.io/esphome/esphome:2026.11.0
docker run --rm --name "soundsense-tests-$$" -v "$PWD":/config -w /config \
  --entrypoint bash "$image" -c 'python3 tests/test_pcm.py'
docker run --rm --name "soundsense-blueprints-$$" -v "$PWD":/config -w /config \
  --entrypoint python3 ghcr.io/home-assistant/home-assistant:2026.11.2 tests/test_blueprints.py
for fixture in tests/fixtures/pdm-player.yaml tests/fixtures/stereo-player.yaml tests/fixtures/speaker-only.yaml; do
  docker run --rm --name "soundsense-validate-$$" -v "$PWD":/config "$image" config "$fixture" >/dev/null
  docker run --rm --name "soundsense-compile-$$" -v "$PWD":/config "$image" compile "$fixture"
done
