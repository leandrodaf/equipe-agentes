#!/usr/bin/env bash
# A sessão de um agente está rodando? Sai 0 (e imprime "vivo") se sim; 1 ("parado") se não.
#   equipe vivo claude-1 | codex-2 | deep-1 | analista
# Use este script em vez de `pgrep -f "SEU NOME: …"` direto no terminal: o pgrep casa com
# qualquer processo que tenha o texto (o próprio shell, um grep, o tmux) e dá "vivo" à toa.
set -uo pipefail
source "$(dirname "$0")/comum.sh"
nome="${1:?uso: equipe vivo <nome>}"
if [[ ! "$nome" =~ ^(analista|(claude|codex|deep)-[0-9]+)$ ]]; then
	echo "nome desconhecido: $nome" >&2; exit 2
fi
# Só conta o claude/codex/deep aberto com o prompt do agente (regra em lib/identidade.py): um
# Claude ou Codex aberto para outra coisa, um grep com o texto do prompt ou o tmux não contam.
if "$LIB/identidade.py" vivo "$nome"; then echo vivo; else echo parado; exit 1; fi
