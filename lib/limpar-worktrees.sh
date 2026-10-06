#!/usr/bin/env bash
# Apaga as pastas de worktree que não fazem mais falta. Nunca perde código:
#  - tudo já na main, item fora da fila viva (ou integrado) → apaga a pasta e a branch;
#  - item arquivado com commits fora da main → apaga só a pasta; a branch fica (dá para
#    recriar a pasta com `git worktree add <pasta> <branch>`).
# Mantém (e diz por quê): mudança não commitada, pasta em uso, item ainda vivo na fila
# (PROPOSTO/EM ANDAMENTO/PRONTO/AJUSTE/APROVADO sem integrar) com trabalho fora da main.
#   equipe limpar-worktrees           só mostra o que faria
#   equipe limpar-worktrees --apagar  apaga de verdade
set -uo pipefail
source "$(dirname "$0")/comum.sh"
APAGAR=0; [[ "${1:-}" == --apagar ]] && APAGAR=1
cd "$RAIZ" || exit 1

status_item() { # status do item na fila viva; vazio se não está lá (arquivado)
	awk -v t="## $PREFIXO-$1 " 'index($0, t) == 1 {f = 1; next} f && /^## / {exit} f && /^- Status:/ {sub(/^- Status: */, ""); print; exit}' "$FILA" 2>/dev/null
}
integrado() { # o Registro do item na fila viva diz "integrado em"
	awk -v t="## $PREFIXO-$1 " 'index($0, t) == 1 {f = 1; next} f && /^## / {exit} f && /integrado em/ {print "s"; exit}' "$FILA" 2>/dev/null
}

em_uso() { # algum processo com o diretório atual dentro da pasta
	local d
	for d in /proc/[0-9]*/cwd; do
		[[ "$(readlink "$d" 2>/dev/null)/" == "$1/"* ]] && return 0
	done
	return 1
}

apagadas=0 mantidas=0
while read -r chave valor; do
	case "$chave" in
	worktree) pasta=$valor branch="" ;;
	branch) branch=${valor#refs/heads/} ;;
	"")
		[[ "$pasta" == "$RAIZ" || -z "$pasta" ]] && continue
		nome=$(basename "$pasta")
		if [[ ! -d "$pasta" ]]; then
			((APAGAR)) && git worktree prune
			echo "apagar  $nome (a pasta já não existe; só o registro)"; ((apagadas++)); continue
		fi
		# Git quebrado na pasta (objeto vazio depois de desligar a máquina): os arquivos dela podem
		# ser a única cópia do trabalho. Nunca apagar.
		if ! git -C "$pasta" rev-parse --verify -q HEAD^{commit} >/dev/null 2>&1 ||
			! git -C "$pasta" status --porcelain >/dev/null 2>&1 ||
			! git -C "$pasta" cherry "$RAMO" HEAD >/dev/null 2>&1; then
			echo "manter  $nome: git com erro (commit corrompido?); os arquivos podem ser a única cópia"; ((mantidas++)); continue
		fi
		if [[ -n "$(git -C "$pasta" status --porcelain 2>/dev/null)" ]]; then
			echo "manter  $nome: mudança não commitada"; ((mantidas++)); continue
		fi
		if em_uso "$pasta"; then
			echo "manter  $nome: em uso por um processo"; ((mantidas++)); continue
		fi
		# commits que não estão na main (nem com o mesmo conteúdo, depois de um rebase)
		fora=$(git -C "$pasta" cherry "$RAMO" HEAD 2>/dev/null | grep -c '^+')
		num=$(grep -oiE "$PREFIXO_MIN-[0-9]+" <<<"$branch" | head -1 | cut -d- -f2)
		status=""; [[ -n "$num" ]] && status=$(status_item "$num")
		if [[ -n "$status" && -z "$(integrado "$num")" ]]; then
			echo "manter  $nome: $PREFIXO-$num ainda na fila ($status)"; ((mantidas++)); continue
		fi
		if ((fora)) && [[ -z "$num" || -n "$status" ]]; then
			echo "manter  $nome: $fora commit(s) fora do $RAMO${num:+ ($PREFIXO-$num integrado, confira)}"; ((mantidas++)); continue
		fi
		so_pasta=0
		if ((fora)); then
			so_pasta=1
			echo "apagar  $nome (só a pasta; a branch $branch fica com $fora commit(s)): $PREFIXO-$num arquivado"
		else
			echo "apagar  $nome${branch:+ (branch $branch)}: tudo já está no $RAMO"
		fi
		((apagadas++))
		if ((APAGAR)); then
			git worktree remove --force "$pasta" &&
				[[ -n "$branch" ]] && ((!so_pasta)) && git branch -D "$branch" >/dev/null
		fi
		;;
	esac
done < <(git worktree list --porcelain)

((APAGAR)) && git worktree prune
echo "---"
if ((APAGAR)); then echo "apagadas: $apagadas · mantidas: $mantidas"
else echo "apagaria: $apagadas · manteria: $mantidas (rode com --apagar)"; fi
