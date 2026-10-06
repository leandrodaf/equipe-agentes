#!/usr/bin/env bash
# Teste de ponta a ponta do supervisor de limites, com sessões REAIS do Claude e do Codex.
# Rode de dentro de um projeto já iniciado (equipe iniciar), de preferência um de teste:
#   testes/e2e-supervisor.sh               → limites (abaixo)
#   testes/e2e-supervisor.sh despertador   → despertador: agente parado recebe DESPERTADOR e responde;
#                                               sessão do Claude travada (kill -STOP) é reiniciada após 2 sem resposta
# Abre claude-91, codex-91 e uma analista de teste (prompts que só obedecem à PAUSA, gastam pouco),
# força limites falsos e confere, pelos processos vivos, cada decisão:
#   1. tudo ok              → analista no Claude, claude-91, codex-91 e deep-91 (DeepSeek) abertos
#   2. de novo, sem mudança → nada muda
#   3. Claude crítico (90%) → analista muda para o Codex; os implementadores ficam
#   4. Claude esgotado      → claude-91 para (pelo parar.sh, confirmando a parada)
#   5. Claude ok de novo    → claude-91 reabre e a analista volta para o Claude
#   6. tudo esgotado        → todos param
# Só roda com a equipe do projeto parada (nenhum agente vivo, sem a sessão tmux dela) e devolve o
# estado como estava (config do supervisor, prompts, diário e caixa da analista, mensagens).
set -uo pipefail
MODO="${1:-limites}"

source "$(dirname "$0")/../lib/comum.sh"
export PATH="$EQUIPE_HOME/bin:$PATH"
TMP="$(mktemp -d)"
V=$'\033[32m' R=$'\033[31m' B=$'\033[1m' N=$'\033[0m'

if [[ -n "$("$LIB/identidade.py" vivos)" ]] || tmux has-session -t "=$SESSAO_TMUX" 2>/dev/null; then
	echo "Há agentes ou a sessão tmux '$SESSAO_TMUX' rodando: este teste só roda com a equipe parada." >&2
	exit 2
fi

# Guarda o que o teste pode tocar e devolve no fim (inclusive com Ctrl+C).
GUARDAR=(supervisor.json supervisor-estado.json supervisor.log analista.md mensagens.log caixa prompts parada)
mkdir -p "$TMP/bak"
for f in "${GUARDAR[@]}"; do [[ -e "$ESTADO/$f" ]] && cp -a "$ESTADO/$f" "$TMP/bak/"; done
limpar() {
	for n in claude-91 codex-91 deep-91 analista; do
		for p in $("$LIB/identidade.py" pids "$n"); do kill -KILL "$p" 2>/dev/null; done
	done
	tmux kill-session -t "=$SESSAO_TMUX" 2>/dev/null
	for f in "${GUARDAR[@]}"; do
		rm -rf "${ESTADO:?}/$f"
		[[ -e "$TMP/bak/$f" ]] && cp -a "$TMP/bak/$f" "$ESTADO/"
	done
	rm -f "$ESTADO/claude-91.md" "$ESTADO/codex-91.md" "$ESTADO/deep-91.md"
	rm -rf "$TMP"
}
trap limpar EXIT

# Prompts de teste: o cabeçalho de identidade é posto pelo lib/prompt.py; o papel vem do nome do arquivo.
mkdir -p "$TMP/papeis"
cat >"$TMP/papeis/teste.md" <<'FIM'
Isto é um TESTE do supervisor de limites. Não rode comandos e não mexa no repositório.
Responda só "pronto, aguardando" e espere.
Se uma mensagem pedir para ler a sua caixa (um arquivo caixa/NOME.md), leia a última linha dela.
Se chegar uma mensagem de PAUSA (direto ou pela caixa), rode só estes dois comandos (troque NOME pelo seu nome, da linha SEU NOME acima):
equipe parada NOME "recebi a pausa (teste)"
equipe parada NOME parado "teste do supervisor"
Não escreva diário, não faça commit, não faça mais nada.
FIM
cat >"$TMP/papeis/analista-teste.md" <<'FIM'
TESTE do supervisor de limites. Não leia arquivos, não rode comandos e não mexa no repositório.
Responda só "analista de teste aguardando" e espere. Ignore qualquer mensagem que chegar.
FIM
if [[ "$MODO" == despertador ]]; then
	cat >"$ESTADO/supervisor.json" <<'EOF'
{"ativo": true, "implementadores": {"claude": 0, "codex": 1, "deep": 0}, "primeiro": 91,
 "analista": ["claude", "codex"], "parar_em": 95, "intervalo_s": 60, "espera_reabrir_s": 0,
 "despertar_analista_min": 1, "despertar_implementador_min": 1, "reiniciar_apos": 2}
EOF
else
	cat >"$ESTADO/supervisor.json" <<'EOF'
{"ativo": true, "implementadores": {"claude": 1, "codex": 1, "deep": 1}, "primeiro": 91,
 "analista": ["claude", "codex"], "parar_em": 95, "intervalo_s": 60, "espera_reabrir_s": 0}
EOF
fi
rm -f "$ESTADO/supervisor-estado.json"

export SUPERVISOR_IGNORAR_PAUSA=1 SUPERVISOR_LIMITES="$TMP/limites.json"
export PAPEL_IMPLEMENTADOR="$TMP/papeis/teste.md" PAPEL_ANALISTA="$TMP/papeis/analista-teste.md"
export ESPERA=180 INTERROMPER=60 GRACA_ANALISTA=20

limites() { # claude_nivel claude_uso codex_nivel codex_uso [deep_nivel]
	python3 - "$@" >"$SUPERVISOR_LIMITES" <<'EOF'
import json, sys
a = sys.argv[1:]
r = lambda n, u: {"nivel": n, "recomendacao": "teste", "janelas": [{"nome": "semana", "usado": float(u), "reset": None, "reset_txt": ""}]}
print(json.dumps({"claude": r(a[0], a[1]), "codex": r(a[2], a[3]), "deep": {"nivel": a[4] if len(a) > 4 else "ok", "janelas": [], "recomendacao": "teste", "saldo_txt": "US$ teste"}}))
EOF
}

vivos() { # "nome:ferramenta" ordenado, pelos processos (a mesma leitura do supervisor)
	python3 -c "import sys; sys.path.insert(0, '$LIB'); import supervisor
print(' '.join(sorted(f'{n}:{f}' for n, f in supervisor.vivos().items())))"
}

falhas=0
passo() { # descrição esperado
	local desc="$1" esperado="$2" agora=""
	echo "${B}== $desc${N}"
	"$LIB/supervisor.py" uma-vez | sed 's/^/   supervisor: /'
	for _ in $(seq 1 20); do # a sessão leva alguns segundos para subir ou sumir
		agora="$(vivos)"
		[[ "$agora" == "$esperado" ]] && break
		sleep 3
	done
	if [[ "$agora" == "$esperado" ]]; then
		echo "   ${V}ok${N}: vivos = ${agora:-nenhum}"
	else
		echo "   ${R}FALHOU${N}: esperado '${esperado:-nenhum}', vivos '${agora:-nenhum}'"
		falhas=$((falhas + 1))
	fi
}

ultimo() { # nome → hora do último evento DO agente (fala, comando, fim de vez)
	python3 -c "import sys; sys.path.insert(0, '$LIB'); import supervisor
a, _ = supervisor.atividade(['$1']); print(a.get('$1', {}).get('h', ''))"
}
confere() { # descrição condição(0/1)
	if (($2)); then echo "   ${V}ok${N}: $1"; else echo "   ${R}FALHOU${N}: $1"; falhas=$((falhas + 1)); fi
}

if [[ "$MODO" == despertador ]]; then
	export ESPERA=60 INTERROMPER=20
	limites ok 10 ok 10
	passo "D1. abre analista e codex-91" "analista:claude codex-91:codex"
	sleep 45
	antes_a=$(ultimo analista) antes_c=$(ultimo codex-91)
	sleep 30 # parados há mais de 1 min (o limite deste teste)
	echo "${B}== D2. os dois parados recebem o DESPERTADOR e respondem${N}"
	saida=$("$LIB/supervisor.py" uma-vez); sed 's/^/   supervisor: /' <<<"$saida"
	confere "despertador enviado à analista" "$(grep -c 'despertador para analista' <<<"$saida")"
	confere "despertador enviado ao codex-91" "$(grep -c 'despertador para codex-91' <<<"$saida")"
	sleep 45
	confere "analista respondeu (último evento $antes_a → $(ultimo analista))" "$([[ "$(ultimo analista)" != "$antes_a" ]] && echo 1 || echo 0)"
	confere "codex-91 respondeu (último evento $antes_c → $(ultimo codex-91))" "$([[ "$(ultimo codex-91)" != "$antes_c" ]] && echo 1 || echo 0)"
	# Sessão travada de verdade: Claude processa tudo no próprio processo. (No Codex, o kill -STOP congela só a
	# tela: o `codex queue` entrega e a resposta sai em outro processo; aí o despertador vê resposta e não reinicia.)
	echo "${B}== D3. analista (Claude) travada (kill -STOP): 2 despertadores sem resposta e a sessão é reiniciada${N}"
	travados=$("$LIB/identidade.py" pids analista | tr '\n' ' ')
	kill -STOP $travados
	echo "   travados: $travados"
	reiniciou=0
	for i in 1 2 3 4; do
		sleep 70
		saida=$("$LIB/supervisor.py" uma-vez); sed 's/^/   supervisor: /' <<<"$saida"
		grep -q 'reiniciar analista' <<<"$saida" && { reiniciou=1; break; }
	done
	confere "supervisor reiniciou a analista" "$reiniciou"
	sleep 10
	novos=$("$LIB/identidade.py" pids analista | tr '\n' ' ')
	confere "analista viva de novo com processo novo ($novos)" "$([[ -n "${novos// /}" ]] && ! grep -qw -F -f <(tr ' ' '\n' <<<"$travados" | grep .) <<<"$novos" && echo 1 || echo 0)"
	antes_a=$(ultimo analista); sleep 40
	confere "a sessão nova trabalha (último evento $antes_a → $(ultimo analista))" "$([[ -n "$(ultimo analista)" ]] && echo 1 || echo 0)"
	echo "--- log do supervisor neste teste:"
	sed 's/^/   /' "$ESTADO/supervisor.log" 2>/dev/null
	echo
	if ((falhas)); then echo "${R}${B}$falhas verificação(ões) falharam${N}"; exit 1; fi
	echo "${V}${B}despertador: tudo passou${N}"
	exit 0
fi

limites ok 10 ok 10
passo "1. tudo ok: abre a equipe" "analista:claude claude-91:claude codex-91:codex deep-91:deep"
sleep 40 # deixa as sessões lerem o prompt antes de receberem a pausa
passo "2. de novo, nada muda" "analista:claude claude-91:claude codex-91:codex deep-91:deep"
limites critico 90 ok 10
passo "3. Claude crítico: analista vai para o Codex" "analista:codex claude-91:claude codex-91:codex deep-91:deep"
limites esgotado 100 ok 10
passo "4. Claude esgotado: claude-91 para (o deep-91 é outra conta e segue)" "analista:codex codex-91:codex deep-91:deep"
grep -h PARADO "$ESTADO/parada/claude-91.log" 2>/dev/null | sed 's/^/   parada confirmada pelo claude-91: /' || echo "   (claude-91 não confirmou a parada; foi fechado pelo tempo)"
limites ok 5 ok 10
passo "5. Claude ok de novo: reabre e a analista volta" "analista:claude claude-91:claude codex-91:codex deep-91:deep"
sleep 40
limites esgotado 100 esgotado 100 esgotado
passo "6. tudo esgotado: todos param" ""
grep -h PARADO "$ESTADO/parada/deep-91.log" 2>/dev/null | sed 's/^/   parada confirmada pelo deep-91: /' || echo "   (deep-91 não confirmou a parada; foi fechado pelo tempo)"
grep -h PARADO "$ESTADO/parada/codex-91.log" 2>/dev/null | sed 's/^/   parada confirmada pelo codex-91: /' || echo "   (codex-91 não confirmou a parada; foi fechado pelo tempo)"
echo "--- log do supervisor neste teste:"
cat "$ESTADO/supervisor.log" 2>/dev/null | sed 's/^/   /'

echo
if ((falhas)); then echo "${R}${B}$falhas passo(s) falharam${N}"; exit 1; fi
echo "${V}${B}todos os passos passaram${N}"
