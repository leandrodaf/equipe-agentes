#!/usr/bin/env bash
# Pausa e retomada da equipe inteira. Quem manda é o analista (a pedido do dono).
#   equipe pausar "motivo"   cria .equipe/estado/PAUSA e avisa todos
#   equipe retomar           apaga a PAUSA e avisa todos
#   equipe pausa ver         quem ainda está trabalhando (travas, testes, servidores)
# Os Codex recebem na hora (codex queue); os Claude, digitado no terminal pelo msg.sh (ou na
# caixa de entrada, sem sessão viva). Quem perder a mensagem vê a PAUSA no início do passo.
set -uo pipefail

source "$(dirname "$0")/comum.sh"
export AGENTE="${AGENTE:-analista}"

implementadores() { # vivos agora (processo com o prompt) + quem mexeu no diário nas últimas 24 h
	{
		"$LIB/identidade.py" vivos
		find "$ESTADO" -maxdepth 1 -name '*.md' -mtime -1 -printf '%f\n' | sed 's/\.md$//'
	} | grep -E '^(claude|codex|deep)-[0-9]+$' | sort -u
}

avisar_todos() { # cada um uma vez: terminal (tmux), fila do Codex ou caixa
	for n in $(implementadores) analista; do "$LIB/msg.sh" "$n" "$1" | sed "s/^/  /"; done
}

texto_pausa() {
	echo "PAUSA ($1). O dono está acompanhando a sua parada ao vivo: relate CADA passo com equipe parada <SEU NOME> \"passo\". Faça, nesta ordem: (1) equipe parada <SEU NOME> \"recebi a pausa; terminando <o que está fazendo>\"; (2) termine só o passo atual (não comece outro); (3) commit WIP na sua worktree (nunca stash) e relate o hash; (4) solte as travas que estiver segurando e relate; (5) derrube os SEUS servidores (fuser -k nas suas portas), mantenha o seu ambiente de teste (dados, cópia de banco); (6) escreva no diário 'pausado: <item, onde parou, próximo passo>'; (7) equipe parada <SEU NOME> parado \"<item e onde parou>\". Depois disso não faça mais nada até RETOMAR."
}

case "${1:-ver}" in
texto) texto_pausa "${2:-pedido do dono}" ;; # usado pelo parar.sh
pausar)
	motivo="${2:-pedido do dono}"
	# Relatos de uma pausa que já está valendo continuam (quem já confirmou não precisa repetir).
	[[ -f "$ESTADO/PAUSA" ]] || rm -rf "$ESTADO/parada"
	mkdir -p "$ESTADO/parada"
	avisar_todos "$(texto_pausa "$motivo")"
	printf '%s\n%s\n' "$(date '+%F %H:%M')" "$motivo" >"$ESTADO/PAUSA"
	echo "PAUSA gravada e enviada a todos pelo msg.sh."
	;;
retomar)
	rm -f "$ESTADO/PAUSA"
	avisar_todos "RETOMAR: a pausa acabou. Releia o seu diário e o Protocolo e continue de onde parou (itens em AJUSTE e APROVADO primeiro)."
	echo "Retomado."
	;;
ver)
	[[ -f "$ESTADO/PAUSA" ]] && echo "EM PAUSA desde $(head -1 "$ESTADO/PAUSA"): $(sed -n 2p "$ESTADO/PAUSA")" || echo "sem pausa"
	echo "travas:"; "$LIB/trava.sh" ver | sed 's/^/  /'
	echo "testes e servidores rodando nas worktrees:"
	python3 - "$RAIZ" "$VALIDACAO_REGEX" <<'PY'
import glob, os, re, subprocess, sys
raiz, padrao = sys.argv[1], re.compile(sys.argv[2])
wts = [l[9:] for l in subprocess.run(["git", "-C", raiz, "worktree", "list", "--porcelain"], capture_output=True, text=True).stdout.splitlines() if l.startswith("worktree ") and l[9:] != raiz]
conta = {}
for d in glob.glob("/proc/[0-9]*"):
    try:
        cwd, cmd = os.readlink(d + "/cwd"), open(d + "/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        continue
    wt = next((w for w in wts if (cwd + "/").startswith(w + "/")), None)
    if wt and padrao.search(cmd) and os.path.basename(cmd.split(" ", 1)[0]) not in ("claude", "codex"):
        conta[wt] = conta.get(wt, 0) + 1
for w, n in sorted(conta.items()):
    print(f"  {n}  {os.path.basename(w)}")
PY
	echo "portas dos agentes abertas ($PORTAS_IMPLEMENTADOR e $PORTAS_ANALISTA):"
	ss -ltnH 2>/dev/null | awk '{print $4}' | while read -r end; do
		p=${end##*:}
		for faixa in $PORTAS_IMPLEMENTADOR $PORTAS_ANALISTA; do
			((p >= ${faixa%-*} && p <= ${faixa#*-})) && echo "  $end"
		done
	done
	echo "último sinal de cada um:"
	for n in $(implementadores); do echo "  $n: $(tail -1 "$ESTADO/$n.md" | cut -c1-90)"; done
	;;
*) echo "uso: equipe pausar \"motivo\" | equipe retomar | equipe pausa ver" >&2; exit 2 ;;
esac
