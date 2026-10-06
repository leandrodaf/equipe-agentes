#!/usr/bin/env bash
# O agente relata cada passo da parada; o `equipe parar` mostra isso ao vivo para o dono.
#   equipe parada <SEU NOME> "salvando contexto"
#   equipe parada <SEU NOME> "commit WIP a1b2c3d na worktree"
#   equipe parada <SEU NOME> parado "MEL-152, critério 3 feito; próximo: escrever o teste"
set -euo pipefail
source "$(dirname "$0")/comum.sh"
NOME="${1:?uso: equipe parada <nome> \"passo\" | <nome> parado \"onde parou\"}"
DIR="$ESTADO/parada"
mkdir -p "$DIR"
if [[ "${2:-}" == parado ]]; then
	echo "$(date +%H:%M:%S) PARADO ${3:-}" >>"$DIR/$NOME.log"
else
	echo "$(date +%H:%M:%S) ${2:?falta o passo}" >>"$DIR/$NOME.log"
fi
