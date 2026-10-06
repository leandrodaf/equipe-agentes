#!/usr/bin/env bash
# Acrescenta uma entrada no CHANGELOG do projeto (CHANGELOG do config), no dia de hoje e na seção certa (cria o dia e a seção
# se faltarem, na ordem padrão). Use no commit que integra o item na `main`.
#   equipe changelog Adicionado "Exportar o relatório em PDF (MEL-152)"
#   equipe changelog Corrigido  "Lista compacta não corta mais valores (MEL-125)"
# Seções: Adicionado | Alterado | Corrigido | Removido | "Equipe de agentes"
# Texto: uma linha, do ponto de vista do dono (o que ele vê ou ganha), com o ID do item no fim.
set -euo pipefail
source "$(dirname "$0")/comum.sh"

SECAO="${1:?uso: equipe changelog <Adicionado|Alterado|Corrigido|Removido|\"Equipe de agentes\"> \"texto (ID)\"}"
TEXTO="${2:?falta o texto}"
ARQ="$RAIZ/$CHANGELOG"
[[ -f "$ARQ" ]] || printf '# Changelog\n\n' >"$ARQ"
case "$SECAO" in Adicionado | Alterado | Corrigido | Removido | "Equipe de agentes") ;; *)
	echo "seção inválida: $SECAO (use Adicionado, Alterado, Corrigido, Removido ou \"Equipe de agentes\")" >&2; exit 2 ;;
esac
[[ "$TEXTO" == *$'\n'* ]] && { echo "uma linha só" >&2; exit 2; }

python3 - "$ARQ" "$(date +%F)" "$SECAO" "$TEXTO" <<'PY'
import re, sys
arq, dia, secao, texto = sys.argv[1:]
ORDEM = ["Adicionado", "Alterado", "Corrigido", "Removido", "Equipe de agentes"]
s = open(arq, encoding="utf-8").read()
entrada = f"- {texto.strip()}"
if f"\n## {dia}\n" not in s:  # o dia novo entra antes do primeiro dia existente
    m = re.search(r"^## \d{4}-\d\d-\d\d$", s, re.M)
    pos = m.start() if m else len(s)
    s = s[:pos] + f"## {dia}\n\n" + s[pos:]
ini = s.index(f"\n## {dia}\n") + 1
fim_m = re.search(r"^## \d{4}-\d\d-\d\d$", s[ini + 3:], re.M)
fim = ini + 3 + fim_m.start() if fim_m else len(s)
bloco = s[ini:fim]
if entrada in bloco:
    print("já está no changelog"); sys.exit(0)
if f"### {secao}\n" in bloco:  # acrescenta no fim da seção
    i = bloco.index(f"### {secao}\n")
    prox = re.search(r"^### ", bloco[i + 4:], re.M)
    j = i + 4 + prox.start() if prox else len(bloco)
    corpo = bloco[i:j].rstrip("\n") + f"\n{entrada}\n\n"
    bloco = bloco[:i] + corpo + bloco[j:].lstrip("\n")
else:  # cria a seção na ordem padrão
    depois = [x for x in ORDEM[ORDEM.index(secao) + 1:] if f"### {x}\n" in bloco]
    nova = f"### {secao}\n\n{entrada}\n\n"
    if depois:
        i = bloco.index(f"### {depois[0]}\n")
        bloco = bloco[:i] + nova + bloco[i:]
    else:
        bloco = bloco.rstrip("\n") + "\n\n" + nova
open(arq, "w", encoding="utf-8").write((s[:ini] + bloco.rstrip("\n") + "\n\n" + s[fim:]).rstrip("\n") + "\n")
print(f"changelog: {dia} · {secao} · {texto[:70]}")
PY
