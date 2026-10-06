#!/usr/bin/env bash
# Mensagem entre agentes. O analista é o líder: ele pede, os implementadores fazem e respondem.
#   equipe msg <para> "texto"      para = codex-N | claude-N | deep-N | analista | codex (todos os Codex)
#   equipe msg ver [nome]          últimas mensagens (de todos ou de/para um nome)
# Como cada um entrega:
#   codex-N  → `codex queue` na sessão dele (aberta com o prompt do codex-N; lib/identidade.py);
#   analista, claude-N e deep-N → digitado no terminal dele (tmux); textos longos vão para a caixa
#              .equipe/estado/caixa/<nome>.md com um aviso curto no terminal; sem sessão viva,
#              só a caixa (o analista vigia a dele com um monitor).
# Use sempre este script, também entre sessões Claude: o SendMessage nativo fica retido entre
# sessões com modos de permissão diferentes (o dono teve de recusar).
# Tudo fica em .equipe/estado/mensagens.log.
set -euo pipefail

source "$(dirname "$0")/comum.sh"
LOG="$ESTADO/mensagens.log"
DE="${AGENTE:-${USER:-dono}}"
mkdir -p "$ESTADO/caixa"

if [[ "${1:-}" == ver ]]; then
	[[ -f "$LOG" ]] || exit 0
	if [[ -n "${2:-}" ]]; then grep -F -- "$2" "$LOG" | tail -20; else tail -20 "$LOG"; fi
	exit 0
fi

PARA="${1:?uso: equipe msg <para> \"texto\"}"
TEXTO="${2:?uso: equipe msg <para> \"texto\"}"
AGORA="$(date '+%F %H:%M')"

sessoes_codex() { # "nome uuid" das sessões recentes, só pelo prompt de abertura (lib/identidade.py):
	# um Codex aberto para outra coisa que leu ou citou um prompt de agente não recebe as ordens dele
	"$LIB/identidade.py" sessoes-codex || true
}

sessao_codex() { # UUID da sessão mais recente do agente
	sessoes_codex | awk -v n="$1" '$1 == n { print $2; exit }'
}

na_caixa() { # nome: acrescenta a mensagem na caixa; acima de 200 linhas, as antigas vão para
	# caixa/antigas/<nome>-AAAA-MM.md e ficam as últimas 50 (a do analista chegou a 148 linhas,
	# relidas a cada disparo do monitor)
	local caixa="$ESTADO/caixa/$1.md"
	echo "- $AGORA · de $DE · $TEXTO" >>"$caixa"
	if (($(wc -l <"$caixa") > 200)); then
		mkdir -p "$ESTADO/caixa/antigas"
		head -n -50 "$caixa" >>"$ESTADO/caixa/antigas/$1-$(date +%Y-%m).md" &&
			tail -n 50 "$caixa" >"$caixa.novo" && mv "$caixa.novo" "$caixa"
	fi
}

digitar() { # digita no terminal do agente (tmux) e confirma que saiu da caixa de digitação
	local alvo="$SESSAO_TMUX:$1" txt="${2//$'\n'/ }"
	# Texto longo colado no terminal demora a ser aceito e o Enter se perde: o texto inteiro vai
	# para a caixa de entrada e no terminal vai só um aviso curto (digitado, chega na hora).
	if ((${#txt} > 180)); then
		na_caixa "$1"
		txt="[$DE $(date +%H:%M)] Mensagem nova e prioritária: leia AGORA a última linha de $ESTADO/caixa/$1.md e siga o que ela pede."
	fi
	tmux send-keys -t "$alvo" -l -- "$txt" || return 1
	sleep 0.5
	for _ in 1 2 3 4; do
		tmux send-keys -t "$alvo" Enter
		sleep 1.5
		tmux capture-pane -p -J -t "$alvo" | tail -4 | grep -qF -- "${txt: -20}" || return 0
	done
	return 0
}

entregar() { # nome
	local nome="$1" corpo="[$DE $(date +%H:%M)] $TEXTO" uuid no_tmux=""
	tmux list-windows -t "=$SESSAO_TMUX" -F '#W' 2>/dev/null | grep -qx "$nome" && no_tmux=1
	# 1) Codex: `codex queue` na sessão dele (entra na fila mesmo no meio do trabalho).
	#    Sem janela no tmux, a sessão pode estar morta: aí a fila só é lida quando ela voltar.
	if [[ "$nome" == codex-* ]]; then
		uuid=$(sessao_codex "$nome") || true
		if [[ -n "${uuid:-}" ]] && timeout 60 codex queue --thread "$uuid" --message "$corpo" >/dev/null 2>&1; then
			echo "$AGORA · $DE → $nome (codex queue) · $TEXTO" >>"$LOG"
			if [[ -n "$no_tmux" ]]; then echo "entregue a $nome"; else echo "na fila da sessão de $nome"; fi
			return
		fi
	fi
	# 2) Claude (ou Codex sem fila) aberto pelo `equipe subir`: digita direto no terminal dele.
	if [[ -n "$no_tmux" ]] && digitar "$nome" "$corpo"; then
		echo "$AGORA · $DE → $nome (terminal) · $TEXTO" >>"$LOG"
		echo "entregue a $nome"
		return
	fi
	# 3) Caixa de entrada (o agente lê no início do ciclo; o analista vigia a dele).
	na_caixa "$nome"
	echo "$AGORA · $DE → $nome (caixa) · $TEXTO" >>"$LOG"
	echo "na caixa de $nome"
}

if [[ "$PARA" == codex ]]; then
	# Só quem é da equipe: tem diário (.equipe/estado/<nome>.md) ou está rodando agora. Sessões de
	# agentes de teste (codex-90…99) também têm o prompt e recebiam os avisos (04/10).
	sessoes_codex | awk '!visto[$1]++ { print $1 }' | while read -r n; do
		[[ -f "$ESTADO/$n.md" ]] || "$LIB/vivo.sh" "$n" >/dev/null || continue
		entregar "$n"
	done
else
	entregar "$PARA"
fi
