#!/usr/bin/env bash
# Abre os agentes, um por janela da sessão tmux do projeto, já com o prompt e o nome preenchidos.
#   equipe agentes <claudes> <codex> [analista 0|1] [primeiro número]
#   ex.: equipe agentes 3 3        → claude-1..3 e codex-1..3
#        equipe agentes 1 0 0 4    → só claude-4
#        ANALISTA_FERRAMENTA=codex equipe agentes 0 0 1 → a analista no Codex (padrão: claude)
#        DEEP_N=2 equipe agentes 0 0 → deep-1 e deep-2: Claude Code apontado para a DeepSeek (o comando
#                                     DEEP_COMANDO do config, padrão `claude-deep`), para itens simples
# Terminal: com tela gráfica, uma janela do gnome-terminal presa à sessão tmux "equipe-<projeto>"
# (cada agente vira uma aba na barra do tmux); sem tela, só o tmux (`tmux attach -t equipe-<projeto>`).
set -euo pipefail
source "$(dirname "$0")/comum.sh"

CLAUDES="${1:-0}"
CODEX_N="${2:-0}"
ANALISTA="${3:-0}"
PRIMEIRO="${4:-1}"
DEEP_N="${DEEP_N:-0}"
ANALISTA_FERRAMENTA="${ANALISTA_FERRAMENTA:-claude}"
[[ "$ANALISTA_FERRAMENTA" == claude || "$ANALISTA_FERRAMENTA" == codex ]] || { echo "ANALISTA_FERRAMENTA inválida: $ANALISTA_FERRAMENTA" >&2; exit 2; }
PROMPTS="$ESTADO/prompts"
mkdir -p "$PROMPTS"

for n in "$CLAUDES" "$CODEX_N" "$ANALISTA" "$PRIMEIRO" "$DEEP_N"; do
	[[ "$n" =~ ^[0-9]+$ ]] || { echo "número inválido: $n" >&2; exit 2; }
done
if (( CLAUDES + CODEX_N + ANALISTA + DEEP_N == 0 )); then
	echo "nada para abrir: equipe agentes <claudes> <codex> [analista 0|1] [primeiro] (DEEP_N=N para DeepSeek)" >&2
	exit 2
fi

# Já está rodando? Dois agentes com o mesmo nome quebram as travas e o Registro.
rodando() { "$LIB/identidade.py" vivo "$1"; }

comandos=()
nomes=()
# O launcher de cada agente garante o `equipe` no PATH e o projeto certo, mesmo de dentro de uma worktree.
AMBIENTE="export PATH='$EQUIPE_HOME/bin':\"\$PATH\" EQUIPE_RAIZ='$RAIZ'"

adicionar() { # nome ferramenta papel
	local nome="$1" ferramenta="$2" papel="$3" arq="$PROMPTS/$1.md"
	if rodando "$nome"; then
		echo "pulando $nome: já está rodando" >&2
		return
	fi
	python3 "$LIB/prompt.py" "$papel" "$nome" >"$arq"
	if (($(wc -c <"$arq") > 120000)); then
		echo "o prompt de $nome passou de 120 KB (limite de um argumento no Linux): enxugue o .equipe/projeto.md" >&2
		exit 2
	fi
	local ini="cd '$RAIZ' && $AMBIENTE && export AGENTE=$nome"
	if [[ "$ferramenta" == deep ]]; then
		# DEEP_COMANDO costuma ser uma função do ~/.zshrc (o claude com a URL e a chave da DeepSeek): só existe num zsh interativo.
		comandos+=("$ini && zsh -ic '$DEEP_COMANDO \"\$@\"' $DEEP_COMANDO -n $nome@$PROJETO --dangerously-skip-permissions --permission-mode bypassPermissions $CLAUDE_ARGS \"\$(cat '$arq')\"; exec bash")
	elif [[ "$ferramenta" == claude ]]; then
		comandos+=("$ini && claude -n $nome@$PROJETO --dangerously-skip-permissions --permission-mode bypassPermissions $CLAUDE_ARGS \"\$(cat '$arq')\"; exec bash")
	else
		# Modelo vem do ~/.codex/config.toml; aprovação e sandbox ficam explícitos aqui (YOLO total).
		comandos+=("$ini && codex -C '$RAIZ' --dangerously-bypass-approvals-and-sandbox $CODEX_ARGS \"\$(cat '$arq')\"; exec bash")
	fi
	nomes+=("$nome")
}

# PAPEL_ANALISTA / PAPEL_IMPLEMENTADOR: outro prompt (o teste do supervisor abre agentes que só obedecem à PAUSA).
(( ANALISTA )) && adicionar analista "$ANALISTA_FERRAMENTA" "${PAPEL_ANALISTA:-analista}"
for ((i = PRIMEIRO; i < PRIMEIRO + CLAUDES; i++)); do adicionar "claude-$i" claude "${PAPEL_IMPLEMENTADOR:-implementador}"; done
for ((i = PRIMEIRO; i < PRIMEIRO + CODEX_N; i++)); do adicionar "codex-$i" codex "${PAPEL_IMPLEMENTADOR:-implementador}"; done
for ((i = PRIMEIRO; i < PRIMEIRO + DEEP_N; i++)); do adicionar "deep-$i" deep "${PAPEL_IMPLEMENTADOR:-implementador}"; done

# Painel web da equipe: sobe junto (se ainda não estiver no ar) e mostra o link.
painel() {
	if ! ss -ltnH "sport = :$PAINEL_PORTA" 2>/dev/null | grep -q .; then
		setsid nohup python3 "$EQUIPE_HOME/painel/servidor.py" "$PAINEL_PORTA" >"$ESTADO/painel.log" 2>&1 </dev/null &
		sleep 1
	fi
	printf '\nPainel da equipe: \033[1mhttp://127.0.0.1:%s\033[0m  (tarefas, console de cada agente, mensagens, pausar)\n' "$PAINEL_PORTA"
}

(( ${#nomes[@]} )) || { echo "nenhum agente novo para abrir" >&2; painel; exit 0; }

# O Claude Code pergunta, na primeira vez numa pasta, se ela é confiável (mesmo com
# --dangerously-skip-permissions): o agente fica parado nessa tela até alguém responder.
if [[ " ${nomes[*]} " =~ \ (analista|claude-[0-9]+|deep-[0-9]+)\  ]] && ! python3 - "$RAIZ" <<'PY'
import json, os, sys
try:
    p = json.load(open(os.path.expanduser("~/.claude.json"))).get("projects", {}).get(sys.argv[1], {})
except (OSError, ValueError):
    p = {}
sys.exit(0 if p.get("hasTrustDialogAccepted") else 1)
PY
then
	printf '\033[33maviso:\033[0m o Claude Code ainda não confia em %s: cada agente Claude vai abrir parado na\n' "$RAIZ" >&2
	printf '       pergunta "Is this a project you trust?". Responda na janela dele (tmux attach -t %s)\n' "$SESSAO_TMUX" >&2
	printf '       ou, da próxima vez, abra `claude` uma vez nesta pasta e aceite antes de subir a equipe.\n' >&2
fi

# A máquina pode ter desligado no meio do trabalho: conserta o git antes de alguém começar.
AGENTE=equipe "$LIB/recuperar.sh" | sed 's/^/recuperação: /' || true

# Cada agente roda numa janela da sessão tmux do projeto (é por ela que a analista e o
# `equipe parar` falam com qualquer agente, Claude ou Codex). Fechar a janela não mata os agentes.
for idx in "${!nomes[@]}"; do
	nome="${nomes[$idx]}" lancador="$PROMPTS/${nomes[$idx]}.sh"
	printf '%s\n' "${comandos[$idx]}" >"$lancador"
	if ! tmux has-session -t "=$SESSAO_TMUX" 2>/dev/null; then
		tmux new-session -d -s "$SESSAO_TMUX" -x 220 -y 50 -n "$nome" "bash -l '$lancador'"
	else
		tmux new-window -d -t "=$SESSAO_TMUX:" -n "$nome" "bash -l '$lancador'"
	fi
	sleep 1 # escalona a subida: todos leem a fila e pegam trava ao mesmo tempo
done

# Barra de abas no topo, clicável, com a aba ativa destacada (só nesta sessão).
tmux set-option -t "=$SESSAO_TMUX" mouse on \; \
	set-option -t "=$SESSAO_TMUX" status-position top \; \
	set-option -t "=$SESSAO_TMUX" status-left " $PROJETO " \; \
	set-option -t "=$SESSAO_TMUX" status-left-length 30 \; \
	set-option -t "=$SESSAO_TMUX" status-right ' Ctrl+b n/p troca · Ctrl+b d sai ' \; \
	set-option -t "=$SESSAO_TMUX" status-right-length 40 \; \
	set-window-option -t "=$SESSAO_TMUX" window-status-format ' #I:#W ' \; \
	set-window-option -t "=$SESSAO_TMUX" window-status-current-format '#[reverse,bold] #I:#W ' >/dev/null 2>&1 || true

# Uma janela só: se já tem alguém olhando a sessão (abriu antes), não abre outra.
if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v gnome-terminal >/dev/null \
	&& [[ "${TERMINAL_AGENTES:-}" != tmux ]] && [[ -z "$(tmux list-clients -t "=$SESSAO_TMUX" 2>/dev/null)" ]]; then
	gnome-terminal --window --maximize --title="$SESSAO_TMUX" -- tmux attach -t "=$SESSAO_TMUX" >/dev/null 2>&1 || true
fi
echo "agentes no tmux (ver todos num terminal só: tmux attach -t $SESSAO_TMUX)"
echo "abertos: ${nomes[*]}"
painel
