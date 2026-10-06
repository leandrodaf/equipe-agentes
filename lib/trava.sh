#!/usr/bin/env bash
# Trava entre agentes (mkdir é atômico).
# Uso: equipe trava pegar  <fila|integracao> <seu-nome>
#      equipe trava soltar <fila|integracao> <seu-nome>
#      equipe trava ver
# fila: para escrever no arquivo da fila (FILA do config); integracao: para mudar o ramo principal.
# ("melhorias" é sinônimo de "fila", do nome antigo.)
# "pegar" espera até 3 min; trava esquecida expira (fila: 10 min, integracao: 60 min).
# Trava de antes do último boot (a máquina desligou) ou de agente que não está mais rodando
# é solta na hora: ninguém fica esperando dono morto.
set -uo pipefail
source "$(dirname "$0")/comum.sh"
BASE="$ESTADO/travas"
mkdir -p "$BASE"
acao=${1:-}; nome_trava=${2:-}; agente=${3:-}
if [ "$acao" = ver ]; then
  for t in "$BASE"/*/; do [ -d "$t" ] && echo "$(basename "$t"): $(cat "$t/dono" 2>/dev/null)"; done; exit 0
fi
[ "$nome_trava" = melhorias ] && nome_trava=fila
case "$nome_trava" in fila) exp=10 ;; integracao) exp=60 ;; *) echo "trava desconhecida: $nome_trava" >&2; exit 2 ;; esac
[ -n "$agente" ] || { echo "informe o seu nome" >&2; exit 2; }
T="$BASE/$nome_trava"
orfa() { # 0 se a trava é de antes do boot ou o agente dono não está rodando
  local dono boot criada
  boot=$(date -d "$(uptime -s)" +%s 2>/dev/null) || boot=0
  criada=$(stat -c %Y "$T" 2>/dev/null) || return 1
  (( criada < boot )) && return 0
  dono=$(cut -d' ' -f1 "$T/dono" 2>/dev/null)
  if [[ "$dono" =~ ^(analista|(claude|codex|deep)-[0-9]+)$ ]]; then
    ! "$LIB/identidade.py" vivo "$dono"
  else
    return 1 # dono/sessão manual: só pelo boot ou pela expiração
  fi
}
# Remove a trava velha só se ela ainda é a mesma que foi julgada velha (mesmo inode e hora):
# sem isso, dois agentes que a viam expirada ao mesmo tempo podiam apagar a trava nova que o
# outro acabou de pegar, e os dois seguiam achando que a tinham.
remover_velha() { # $1 = identidade (stat) vista antes do julgamento
  exec 8>"$BASE/.$nome_trava.remocao"
  flock 8
  [ "$(stat -c '%i %Y' "$T" 2>/dev/null)" = "$1" ] && rm -rf "$T"
  flock -u 8
}
case "$acao" in
  pegar)
    for _ in $(seq 90); do
      if mkdir "$T" 2>/dev/null; then echo "$agente $(date '+%F %T')" > "$T/dono"; echo "OK: trava $nome_trava com $agente"; exit 0; fi
      if [ "$(cat "$T/dono" 2>/dev/null | cut -d' ' -f1)" = "$agente" ]; then echo "OK: a trava $nome_trava já é sua"; exit 0; fi
      vista=$(stat -c '%i %Y' "$T" 2>/dev/null) || continue
      if orfa; then
        echo "trava $nome_trava órfã ($(cat "$T/dono" 2>/dev/null): máquina reiniciou ou o agente não está rodando); removendo" >&2; remover_velha "$vista"; continue
      fi
      if [ -n "$(find "$T" -maxdepth 0 -mmin +$exp 2>/dev/null)" ]; then
        echo "trava $nome_trava expirada ($(cat "$T/dono" 2>/dev/null)); removendo" >&2; remover_velha "$vista"; continue
      fi
      sleep 2
    done
    echo "OCUPADA: $nome_trava com $(cat "$T/dono" 2>/dev/null); tente de novo depois" >&2; exit 1 ;;
  soltar)
    if [ "$(cat "$T/dono" 2>/dev/null | cut -d' ' -f1)" = "$agente" ]; then rm -rf "$T"; echo "OK: trava $nome_trava solta"; else echo "a trava $nome_trava não é sua (dono: $(cat "$T/dono" 2>/dev/null || echo ninguém)); nada feito" >&2; exit 1; fi ;;
  *) echo "uso: equipe trava pegar|soltar <fila|integracao> <nome> | equipe trava ver" >&2; exit 2 ;;
esac
