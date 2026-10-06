#!/usr/bin/env bash
# Árvore principal sem mudança pendente, sem perder nada.
# Uso: equipe arvore ver                 (sai 0 se limpa; 1 se suja, e lista)
#      equipe arvore resgatar <seu-nome> (guarda as mudanças numa branch e limpa)
#
# "resgatar" só age com a trava de integração na mão (quem mexe na main é um só) e só
# em mudança parada há mais de 15 min (alguém pode estar editando agora). As mudanças
# vão para a branch resgate/<data-hora> e para .equipe/estado/resgates/<data-hora>.patch;
# nada é apagado sem cópia. Não usa git stash (é compartilhado entre worktrees).
set -uo pipefail
source "$(dirname "$0")/comum.sh"
MINUTOS=15
cd "$RAIZ" || exit 2
acao=${1:-ver}; agente=${2:-}

# Merge/rebase/cherry-pick que ficou pela metade na árvore principal.
operacao_pendente() {
  local g; g=$(git rev-parse --git-dir)
  for f in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
    [ -e "$g/$f" ] && { echo "$f"; return 0; }
  done
  return 1
}

sujos() { git status --porcelain --untracked-files=no | cut -c4- | sed 's/^.* -> //'; }

case "$acao" in
  ver)
    op=$(operacao_pendente) && echo "operação pela metade: $op"
    lista=$(sujos)
    if [ -z "$lista" ] && [ -z "${op:-}" ]; then echo "LIMPA"; exit 0; fi
    echo "SUJA:"; git status --short --untracked-files=no
    exit 1 ;;
  resgatar)
    [ -n "$agente" ] || { echo "informe o seu nome" >&2; exit 2; }
    dono=$(cut -d' ' -f1 "$ESTADO/travas/integracao/dono" 2>/dev/null)
    [ "$dono" = "$agente" ] || { echo "pegue antes a trava de integração (equipe trava pegar integracao $agente)" >&2; exit 2; }
    if op=$(operacao_pendente); then
      case "$op" in
        MERGE_HEAD) git merge --abort ;;
        CHERRY_PICK_HEAD) git cherry-pick --abort ;;
        REVERT_HEAD) git revert --abort ;;
        *) git rebase --abort ;;
      esac
      echo "abortado: $op que ficou pela metade"
    fi
    lista=$(sujos)
    [ -z "$lista" ] && { echo "LIMPA"; exit 0; }
    recente=$(while IFS= read -r f; do [ -e "$f" ] && find "$f" -maxdepth 0 -mmin -$MINUTOS; done <<<"$lista")
    if [ -n "$recente" ]; then
      echo "ESPERE: arquivo mexido há menos de $MINUTOS min (alguém pode estar editando):" >&2
      echo "$recente" >&2; exit 1
    fi
    ts=$(date +%Y%m%d-%H%M%S)
    mkdir -p "$ESTADO/resgates"
    git diff HEAD > "$ESTADO/resgates/$ts.patch"
    idx=$(mktemp)
    GIT_INDEX_FILE=$idx git read-tree HEAD
    GIT_INDEX_FILE=$idx git add -u
    arvore=$(GIT_INDEX_FILE=$idx git write-tree)
    rm -f "$idx"
    commit=$(git commit-tree "$arvore" -p HEAD -m "resgate: mudanças pendentes na árvore principal ($ts, por $agente)")
    git branch "resgate/$ts" "$commit" || { echo "não consegui criar a branch de resgate; nada foi limpo" >&2; exit 1; }
    while IFS= read -r f; do git restore --source=HEAD --staged --worktree -- "$f"; done <<<"$lista"
    echo "RESGATADO em resgate/$ts (patch: $ESTADO/resgates/$ts.patch):"
    echo "$lista"
    git status --porcelain --untracked-files=no | grep -q . && { echo "ainda suja depois do resgate" >&2; exit 1; }
    echo "LIMPA" ;;
  *) echo "uso: equipe arvore ver | resgatar <seu-nome>" >&2; exit 2 ;;
esac
