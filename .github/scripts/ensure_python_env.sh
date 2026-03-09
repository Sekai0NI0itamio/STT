#!/usr/bin/env bash
set -euo pipefail

extras="${1:-base}"
mode="${2:-repair-missing}"
venv_dir="${VENV_DIR:-.venv}"
venv_python="$venv_dir/bin/python"
venv_pip="$venv_dir/bin/pip"

case "$mode" in
  cached|repair-missing|reinstall)
    ;;
  *)
    echo "Unsupported dependency mode: $mode" >&2
    exit 1
    ;;
esac

case "$extras" in
  base)
    install_spec='.'
    required_modules=()
    ;;
  runtime)
    install_spec='.[runtime]'
    required_modules=(faster_whisper pydub)
    ;;
  dev)
    install_spec='.[dev]'
    required_modules=(ruff)
    ;;
  *)
    echo "Unsupported extras set: $extras" >&2
    exit 1
    ;;
esac

if [[ "$mode" == "reinstall" && -d "$venv_dir" ]]; then
  rm -rf "$venv_dir"
fi

if [[ ! -x "$venv_python" ]]; then
  python -m venv "$venv_dir"
fi

"$venv_python" -m pip install --upgrade pip setuptools wheel

needs_install=0
if [[ "$mode" == "reinstall" ]]; then
  needs_install=1
elif [[ ${#required_modules[@]} -eq 0 ]]; then
  if [[ ! -e "$venv_dir/.base-ready" ]]; then
    needs_install=1
  fi
else
  for module_name in "${required_modules[@]}"; do
    if ! "$venv_python" -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('$module_name') else 1)"; then
      needs_install=1
      break
    fi
  done
fi

if [[ "$needs_install" -eq 1 ]]; then
  "$venv_pip" install "$install_spec"
fi

if [[ "$extras" == "base" ]]; then
  touch "$venv_dir/.base-ready"
fi
