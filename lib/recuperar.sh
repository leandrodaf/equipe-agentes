#!/usr/bin/env bash
# Conserta o git depois de a máquina desligar no meio do trabalho. Rode no início de toda
# sessão (passo 0); é rápido e não faz nada se estiver tudo bem. Nunca apaga arquivo de trabalho:
#  - .lock largado por git morto (index.lock, HEAD.lock…) → apaga, se nenhum git estiver rodando;
#  - objeto vazio em .git/objects (gravação cortada) → apaga e busca de novo no GitHub;
#  - branch apontando para commit quebrado → volta para o último commit íntegro do reflog; o que
#    veio depois continua nos arquivos da worktree e aparece como mudança não commitada;
#  - índice quebrado numa worktree → refaz o índice a partir do HEAD (os arquivos ficam);
#  - rebase/merge pela metade numa worktree → só avisa (o dono da worktree decide).
#   equipe recuperar            (imprime "OK: git íntegro" ou o que consertou)
set -uo pipefail
export LC_ALL=C
source "$(dirname "$0")/comum.sh"
GIT="$RAIZ/.git"
LOG="$ESTADO/recuperacao.log"
cd "$RAIZ" || exit 1
exec 9>"$ESTADO/recuperar.lock"
flock 9 # dois agentes ao mesmo tempo: o segundo espera e encontra tudo já consertado

feitos=0
relata() { echo "$1"; echo "$(date '+%F %H:%M') · ${AGENTE:-?} · $1" >>"$LOG"; ((feitos++)); }
integro() { # commit legível com a árvore inteira legível
	git cat-file -e "$1^{commit}" 2>/dev/null && git ls-tree -r "$1" >/dev/null 2>&1
}

# 1) travas do próprio git largadas por um processo que morreu
if ! pgrep -x git >/dev/null; then
	while IFS= read -r l; do
		rm -f "$l" && relata "apaguei trava largada do git: ${l#"$GIT"/}"
	done < <(find "$GIT" -name '*.lock' -type f -not -path '*/objects/*' 2>/dev/null)
fi

# 2) objetos vazios: ilegíveis, só atrapalham. O que estava no GitHub volta pelo fetch.
vazios=$(find "$GIT/objects" -type f -empty 2>/dev/null | wc -l)
if ((vazios)); then
	find "$GIT/objects" -type f -empty -delete
	relata "apaguei $vazios objeto(s) vazio(s) do git (gravação cortada)"
	git fetch -q origin 2>/dev/null || true
fi

# 3) branch com commit quebrado → último commit íntegro do reflog
while IFS= read -r ref; do
	sha=$(cat "$GIT/$ref" 2>/dev/null || git rev-parse -q "$ref" 2>/dev/null)
	[[ -n "$sha" ]] && integro "$sha" && continue
	bom=""
	if [[ -f "$GIT/logs/$ref" ]]; then
		while read -r _ novo _; do
			[[ "$novo" =~ ^[0-9a-f]{40}$ ]] && integro "$novo" && { bom=$novo; break; }
		done < <(tr -d '\0' <"$GIT/logs/$ref" | tac)
	fi
	if [[ -n "$bom" ]]; then
		git update-ref "$ref" "$bom" &&
			relata "${ref#refs/heads/}: commit quebrado; voltei para $(git log -1 --format='%h %s' "$bom" | cut -c1-80). O trabalho depois disso está nos arquivos da worktree, como mudança não commitada: confira e commite de novo"
	else
		relata "${ref#refs/heads/}: commit quebrado e nenhum commit íntegro no reflog; os arquivos da worktree são a única cópia, não apague a pasta"
	fi
done < <(git for-each-ref --format='%(refname)' refs/heads 2>/dev/null)

# 4) worktrees: índice quebrado e operação pela metade
while read -r chave pasta; do
	[[ "$chave" == worktree && -d "$pasta" ]] || continue
	gd=$(git -C "$pasta" rev-parse --git-dir 2>/dev/null) || continue
	meio=""
	for op in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD; do [[ -e "$gd/$op" ]] && meio=$op; done
	if [[ -n "$meio" ]]; then # nunca mexer: o índice guarda o conflito e o estado da operação
		echo "aviso: $(basename "$pasta"): operação pela metade ($meio); o dono da worktree termina (--continue) ou desfaz (--abort)"
		continue
	fi
	# Índice que aponta para objeto que sumiu: o próximo commit falharia. read-tree refaz o
	# índice a partir do HEAD sem tocar nos arquivos (o reset falha lendo o objeto que sumiu).
	if [[ -z "$(git -C "$pasta" ls-files -u 2>/dev/null)" ]] && ! git -C "$pasta" write-tree >/dev/null 2>&1; then
		git -C "$pasta" rev-parse -q --verify HEAD^{commit} >/dev/null 2>&1 &&
			git -C "$pasta" read-tree HEAD 2>/dev/null &&
			relata "$(basename "$pasta"): índice quebrado; refiz a partir do HEAD (arquivos intactos, aparecem como mudança não commitada)"
	fi
done < <(git worktree list --porcelain 2>/dev/null)

((feitos)) || echo "OK: git íntegro"
exit 0
