#!/usr/bin/env bash

pushd ~/workspace/twitch-desktop/ || exit
PYTHONPATH="$PYTHONPATH:$(pwd)" poetry run python ./src/app.py "$@" > /tmp/foo_output 2>&1
popd || exit
