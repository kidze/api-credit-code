#!/bin/sh
# API Credit Code installer for macOS and Linux. In Terminal:
#
#   curl -fsSL https://raw.githubusercontent.com/kidze/api-credit-code/main/install.sh | bash
#
# What it does: installs uv (Astral's Python installer, which also fetches Python if you need it) unless you have
# it, installs API Credit Code for your user with `uv tool install`, adds an app icon (~/Applications on a Mac,
# the app menu on Linux), and opens it in your browser. No sudo. To update, run the same line again.
#
# For testing: ACC_SOURCE installs from another place (a folder or a .zip), ACC_NO_LAUNCH=1 skips the icon and
# runs a self-test instead of opening the app.
set -eu

main() {
    source="${ACC_SOURCE:-https://github.com/kidze/api-credit-code/archive/refs/heads/main.zip}"
    case "$source" in
        *://*) ;;
        *) source="file://$(cd "$source" && pwd)" ;;  # a local folder
    esac
    echo "Installing API Credit Code..."

    if ! command -v claude >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/claude" ]; then
        echo "Claude Code isn't installed yet. Install it too (Anthropic's installer):"
        echo "    curl -fsSL https://claude.ai/install.sh | bash"
    fi

    uv="$(command -v uv 2>/dev/null || true)"
    if [ -z "$uv" ] && [ -x "$HOME/.local/bin/uv" ]; then
        uv="$HOME/.local/bin/uv"
    fi
    if [ -z "$uv" ]; then
        echo "Installing uv (https://docs.astral.sh/uv)..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        uv="$HOME/.local/bin/uv"
    fi

    "$uv" tool install --force --quiet "api-credit-code @ $source"
    app="$("$uv" tool dir --bin)/api-credit-code"
    version="$("$app" --version)"

    if [ -n "${ACC_NO_LAUNCH:-}" ]; then
        "$app" --selftest
    else
        "$app" --make-launcher >/dev/null || echo "No app icon was made (see above). You can start it with: $app"
        if curl -fsS --max-time 2 http://127.0.0.1:8790/api/hello 2>/dev/null | grep -q api-credit-code; then
            echo "An older copy is still running: click Quit at the bottom of its chat list, then open it again."
        else
            nohup "$app" --app >/dev/null 2>&1 </dev/null &
        fi
    fi

    echo ""
    echo "$version is installed."
    if ! command -v api-credit-code >/dev/null 2>&1; then
        echo "To use the api-credit-code command in a terminal, run: $uv tool update-shell (then open a new terminal)"
    fi
    if [ -z "${ACC_NO_LAUNCH:-}" ]; then
        if [ "$(uname)" = "Darwin" ]; then
            echo "It opens in your browser. Next time, open API Credit Code from Applications (in your home folder)."
        else
            echo "It opens in your browser. Next time, open API Credit Code from your app menu, or run: api-credit-code"
        fi
    fi
}

main "$@"
