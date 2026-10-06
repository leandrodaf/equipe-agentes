#!/usr/bin/env bash
# Desliga a equipe inteira com segurança, mostrando ao vivo cada agente parando:
#   codex-2   › recebi a pausa; terminando o teste do MEL-152
#   codex-2   › commit WIP 1a2b3c4 na worktree
#   codex-2   ✔ parado · MEL-152, critério 3 feito; próximo: escrever o teste
# Só fecha as sessões depois que todos confirmarem (ou o tempo acabar, avisando quem ficou).
# Rodar de novo é seguro: quem já confirmou nesta pausa não precisa repetir.
# O app do projeto continua no ar, a não ser com APP=1 (roda o APP_PARAR do config).
#   equipe parar            
#   ESPERA=600 equipe parar (espera no máximo 10 min em vez de 4)
# A pausa só chega ao agente quando o comando dele termina: quem não confirmar em
# INTERROMPER segundos (45) tem os comandos em andamento (teste, instalação, servidor) interrompidos,
# para ler a pausa na hora. O trabalho fica commitado ou na worktree; nada se perde.
set -uo pipefail

source "$(dirname "$0")/comum.sh"
PARADA="$ESTADO/parada"
ESPERA="${ESPERA:-240}"
INTERROMPER="${INTERROMPER:-45}"
GRACA_ANALISTA="${GRACA_ANALISTA:-60}" # o analista não tem trabalho pela metade: fecha sem confirmar após isso
MOTIVO="${MOTIVO:-parar tudo (equipe parar)}"
export AGENTE="${AGENTE:-dono}"
SO="${PARAR_SO:-}" # PARAR_SO="claude-99 codex-99": só esses (para testar sem derrubar a equipe)
B=$'\033[1m' V=$'\033[32m' A=$'\033[33m' C=$'\033[2m' N=$'\033[0m'

# Só sessões abertas com o prompt de agente deste projeto (lib/identidade.py): um Claude ou Codex aberto
# para outra coisa nunca é pausado nem fechado por aqui.
vivos() {
	"$LIB/identidade.py" vivos |
		{ if [[ -n "$SO" ]]; then grep -xF -f <(tr ' ' '\n' <<<"$SO") || true; else cat; fi; }
}
pids_de() { "$LIB/identidade.py" pids "$1"; }
comandos_de() { # shells que o agente abriu para rodar comandos (Bash do Claude, exec do Codex) e tudo abaixo
	local p c
	for p in "$@"; do
		for c in $(pgrep -P "$p"); do
			case "$(ps -o comm= -p "$c")" in
			bash | zsh | sh) echo "$c"; comandos_de_tudo "$c" ;;
			*) comandos_de "$c" ;;
			esac
		done
	done
}
comandos_de_tudo() { local c; for c in $(pgrep -P "$1"); do echo "$c"; comandos_de_tudo "$c"; done; }
ja_parou() { grep -q ' PARADO' "$PARADA/$1.log" 2>/dev/null; }

mapfile -t AGENTES < <(vivos)
if ((${#AGENTES[@]} == 0)); then
	echo "Nenhum agente rodando."
else
	echo "${B}Parando ${#AGENTES[@]} agente(s):${N} ${AGENTES[*]}"
fi

# 1) Pausa: cada um vivo recebe no próprio terminal (tmux), na fila da sessão (Codex) ou na caixa.
[[ -f "$ESTADO/PAUSA" ]] || rm -rf "$PARADA"
mkdir -p "$PARADA"
# Parada parcial (supervisor): é sempre uma parada nova; o PARADO de uma vez anterior não vale.
[[ -n "$SO" ]] && for n in "${AGENTES[@]}"; do rm -f "$PARADA/$n.log"; done
texto=$("$LIB/pausa.sh" texto "$MOTIVO")
for n in "${AGENTES[@]}"; do
	if ja_parou "$n"; then
		echo "  ${V}$n já tinha confirmado a parada${N}"
	else
		printf '  avisando %-9s %s\n' "$n" "$C$("$LIB/msg.sh" "$n" "$texto" 2>&1 | tail -1)$N"
	fi
done
[[ -z "$SO" ]] && printf '%s\n%s\n' "$(date '+%F %H:%M')" "$MOTIVO" >"$ESTADO/PAUSA"
echo "${C}esperando cada um fechar o que está fazendo (até $((ESPERA / 60)) min; Ctrl+C sai sem fechar ninguém)…${N}"

# 2) Acompanha ao vivo, agente por agente, até todos confirmarem.
declare -A lidas=() ok=() interrompido=() ultimo_sinal=() ultimo_console=() resumo=()
inicio=$(date +%s); batida=$inicio
for n in "${AGENTES[@]}"; do lidas[$n]=0; ultimo_sinal[$n]=$inicio; done
while ((${#AGENTES[@]})); do
	pend=()
	agora=$(date +%s)
	for n in "${AGENTES[@]}"; do
		[[ -n "${ok[$n]:-}" ]] && continue
		f="$PARADA/$n.log"
		if [[ -f "$f" ]] && (($(wc -l <"$f") > lidas[$n])); then
			while IFS= read -r l; do
				h=${l%% *} t=${l#* }
				if [[ "$t" == PARADO* ]]; then
					resumo[$n]="${t#PARADO }"; ok[$n]=1
					printf '  %s%-9s ✔ parado%s · %s\n' "$V" "$n" "$N" "${resumo[$n]:-sem resumo}"
				else
					printf '  %-9s › %s %s(%s)%s\n' "$n" "$t" "$C" "$h" "$N"
				fi
			done < <(tail -n +"$((lidas[$n] + 1))" "$f")
			lidas[$n]=$(wc -l <"$f"); ultimo_sinal[$n]=$agora
		fi
		[[ -n "${ok[$n]:-}" ]] && continue
		if [[ -z "$(pids_de "$n")" ]]; then
			ok[$n]=1; resumo[$n]="a sessão fechou sozinha"
			printf '  %s%-9s ✔ fechou%s (a sessão terminou)\n' "$V" "$n" "$N"
			continue
		fi
		if [[ "$n" == analista ]] && ((agora - inicio >= GRACA_ANALISTA)) && ! "$LIB/trava.sh" ver 2>/dev/null | grep -q '^fila: analista'; then
			ok[$n]=1; resumo[$n]="sem trava nem trabalho pela metade; fechado sem esperar mais"
			printf '  %s%-9s ✔ pode fechar%s (não segura trava; o diário dele fica como está)\n' "$V" "$n" "$N"
			continue
		fi
		pend+=("$n")
		# Preso num comando longo: a pausa fica na fila até ele acabar. Interrompe o comando.
		if [[ -z "${interrompido[$n]:-}" ]] && ((agora - inicio >= INTERROMPER)); then
			interrompido[$n]=1
			mapfile -t cmds < <(comandos_de $(pids_de "$n"))
			if ((${#cmds[@]})); then
				printf '  %s%-9s ⏹ interrompendo %s comando(s) em andamento para ele ler a pausa%s\n' "$A" "$n" "${#cmds[@]}" "$N"
				kill -TERM "${cmds[@]}" 2>/dev/null
				sleep 3
				kill -KILL "${cmds[@]}" 2>/dev/null
			fi
		fi
		# Sem relato há 40 s: mostra a última ação do console, para o dono saber o que ele está fazendo.
		if ((agora - ultimo_sinal[$n] >= 40)); then
			c=$(python3 "$EQUIPE_HOME/painel/servidor.py" --ultimo "$n" 2>/dev/null | cut -f2)
			if [[ -n "$c" && "$c" != "${ultimo_console[$n]:-}" ]]; then
				printf '  %-9s %s… %s%s\n' "$n" "$C" "$c" "$N"
				ultimo_console[$n]=$c
			fi
			ultimo_sinal[$n]=$agora
		fi
	done
	((${#pend[@]} == 0)) && break
	if ((agora - batida >= 20)); then # batida: nunca parece travado
		printf '  %s⋯ %s aguardando: %s (há %s s)%s\n' "$C" "$(date +%H:%M:%S)" "${pend[*]}" "$((agora - inicio))" "$N"
		batida=$agora
	fi
	if ((agora - inicio >= ESPERA)); then
		echo "${A}Tempo esgotado ($((ESPERA / 60)) min).${N}"
		break
	fi
	sleep 2
done

# 3) Fecha as sessões (sinal de fechar; se não sair em 5 s, força), o tmux e o painel.
echo "${C}fechando as sessões…${N}"
for n in "${AGENTES[@]}"; do
	tmux kill-window -t "$SESSAO_TMUX:$n" 2>/dev/null
	for p in $(pids_de "$n"); do kill -TERM "$p" 2>/dev/null; done
done
for _ in 1 2 3 4 5; do [[ -z "$(vivos)" ]] && break; sleep 1; done
for n in $(vivos); do for p in $(pids_de "$n"); do kill -KILL "$p" 2>/dev/null; done; done
if [[ -z "$SO" ]]; then
	# O supervisor reabriria a equipe quando os limites voltassem: desliga junto (equipe subir liga de novo).
	[[ -f "$ESTADO/supervisor.pid" ]] && kill "$(cat "$ESTADO/supervisor.pid")" 2>/dev/null && echo "  supervisor de limites desligado"
	tmux kill-session -t "=$SESSAO_TMUX" 2>/dev/null
	fuser -k "$PAINEL_PORTA/tcp" >/dev/null 2>&1
fi

echo
echo "${B}Resumo${N}"
for n in "${AGENTES[@]}"; do
	if [[ -n "${ok[$n]:-}" ]]; then
		printf '  %s✔%s %-9s %s\n' "$V" "$N" "$n" "${resumo[$n]}"
	else
		ult=$(grep -h 'pausado' "$ESTADO/$n.md" 2>/dev/null | tail -1 | cut -c1-100)
		printf '  %s⚠%s %-9s não confirmou; fechado assim mesmo (o diário dele diz: %s)\n' "$A" "$N" "$n" "${ult:-nada}"
		echo "- $(date '+%F %H:%M') · equipe parar: $n não confirmou a parada; sessão fechada" >>"$ESTADO/analista.md"
	fi
done
[[ -n "$(vivos)" ]] && echo "  ${A}ainda vivos: $(vivos | tr '\n' ' ')${N}"
[[ -z "$SO" ]] && echo "  painel fechado"
if [[ "${APP:-0}" == 1 && -z "$SO" && -n "$APP_PARAR" ]]; then
	(cd "$RAIZ" && bash -c "$APP_PARAR") && echo "  app desligado (APP=1)"
elif [[ -n "$APP_URL" && -z "$SO" ]]; then
	echo "  o app continua no ar: $APP_URL${APP_PARAR:+ (desligar também: equipe parar APP=1)}"
fi
echo "Para voltar: equipe subir (cada agente continua do próprio diário)"
