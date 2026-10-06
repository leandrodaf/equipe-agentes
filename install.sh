#!/usr/bin/env bash
# Instala o comando `equipe`: um link de bin/equipe em ~/.local/bin (ou no diretório dado).
#   ./install.sh [destino]
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
DESTINO="${1:-$HOME/.local/bin}"

faltam=()
for c in git tmux python3 ss fuser flock; do command -v "$c" >/dev/null || faltam+=("$c"); done
((${#faltam[@]})) && echo "aviso: falta no PATH: ${faltam[*]}" >&2
command -v claude >/dev/null || command -v codex >/dev/null || echo "aviso: nem claude nem codex no PATH" >&2

mkdir -p "$DESTINO"
ln -sfn "$AQUI/bin/equipe" "$DESTINO/equipe"
echo "instalado: $DESTINO/equipe → $AQUI/bin/equipe"
case ":$PATH:" in *":$DESTINO:"*) ;; *) echo "aviso: $DESTINO não está no PATH" >&2 ;; esac
