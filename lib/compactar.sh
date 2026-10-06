#!/usr/bin/env bash
# Compacta a sessão de um agente numa fronteira de trabalho e o faz continuar o ciclo sozinho.
# O agente chama como ÚLTIMA ação da vez (em segundo plano) e termina a vez:
#   setsid nohup equipe compactar <SEU NOME> "foco: MEL-152 integrado; próximo: pegar da fila" >/dev/null 2>&1 &
# O script espera a sessão ficar parada, digita o /compact (Claude: com o foco; Codex: puro,
# que é o que ele aceita), espera terminar e manda "continue o ciclo".
# Só funciona para agente aberto pelo `equipe subir`/`equipe agentes` (janela no tmux "equipe-<projeto>").
set -uo pipefail

source "$(dirname "$0")/comum.sh"
NOME="${1:?uso: equipe compactar <nome> \"foco\"}"
FOCO="${2:-}"
LOG="$ESTADO/mensagens.log"
ALVO="$SESSAO_TMUX:$NOME"

tmux list-windows -t "=$SESSAO_TMUX" -F '#W' 2>/dev/null | grep -qx "$NOME" || { echo "sem janela $NOME no tmux" >&2; exit 1; }

espera_parar() { # parado = a tela não muda por 8 s (trabalhando, há animação/cronômetro); até 15 min
	local antes="" agora quieto=0 i
	for ((i = 0; i < 450 && quieto < 4; i++)); do
		agora=$(tmux capture-pane -p -t "$ALVO" | tail -15 | md5sum)
		if [[ "$agora" == "$antes" ]]; then quieto=$((quieto + 1)); else quieto=0; fi
		antes=$agora
		sleep 2
	done
}
digita() { tmux send-keys -t "$ALVO" -l -- "$1" && sleep 0.5 && tmux send-keys -t "$ALVO" Enter; }

espera_parar
if [[ "$NOME" == codex-* ]]; then
	digita "/compact"
else
	digita "/compact Mantenha: quem você é ($NOME) e o seu papel; o item atual e o estado dele; branch, worktree, portas e ambiente de teste; decisões tomadas e o próximo passo. ${FOCO} Descarte saídas de comandos, logs e arquivos já lidos."
fi
echo "$(date '+%F %H:%M') · $NOME → $NOME (compactação) · ${FOCO:-sem foco}" >>"$LOG"
sleep 5
espera_parar
digita "Sessão compactada. Continue o ciclo de onde parou: releia o seu diário ($ESTADO/$NOME.md), a sua caixa de entrada e o Protocolo do $FILA. ${FOCO}"
