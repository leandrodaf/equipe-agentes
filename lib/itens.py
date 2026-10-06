#!/usr/bin/env python3
"""Itens da fila (o arquivo FILA do config, padrão MELHORIAS.md).

    equipe itens            ID | Status | Responsável | Depende de  (todos)
    equipe itens PROPOSTO   filtra pelo começo do status ("APROVADO" pega "APROVADO (condição…)")
    equipe itens fila       os próximos a pegar (PROPOSTO sem responsável), na ordem do dono
                            (.equipe/estado/ordem.json, definida no painel), depois P0→P3, depois o número

Um item é um bloco que começa com `## <PREFIXO>-<número> · <título>` e tem linhas `- Campo: valor`.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402


def blocos(texto, prefixo):
    cab = re.compile(rf"## ({re.escape(prefixo)}-(\d+)) · (.*)")
    for bloco in re.split(r"^(?=## )", texto, flags=re.M):
        m = cab.match(bloco)
        if m:
            yield m, bloco


def campo(bloco, nome):
    c = re.search(rf"^- {nome}:\s*(.*)$", bloco, re.M)
    return c.group(1).strip() if c else ""


def main(argv):
    c = config.carregar()
    try:
        texto = open(os.path.join(c["RAIZ"], c["FILA"]), encoding="utf-8").read()
    except OSError:
        print(f"sem fila: {c['FILA']} não existe em {c['RAIZ']}", file=sys.stderr)
        return 1
    if argv[:1] == ["fila"]:
        try:
            ordem = json.load(open(os.path.join(c["ESTADO"], "ordem.json"), encoding="utf-8")).get("ids", [])
        except (OSError, ValueError):
            ordem = []
        fila = []
        for m, bloco in blocos(texto, c["PREFIXO"]):
            if not campo(bloco, "Status").startswith("PROPOSTO") or campo(bloco, "Responsável"):
                continue
            p = re.search(r"P([0-3])", campo(bloco, "Prioridade"))
            pos = ordem.index(m.group(1)) if m.group(1) in ordem else len(ordem)
            fila.append((pos, int(p.group(1)) if p else 9, int(m.group(2)), m.group(1), p.group(0) if p else "-",
                         m.group(3)[:70], campo(bloco, "Depende de")[:60]))
        for i, (_, _, _, id_, pr, tit, dep) in enumerate(sorted(fila), 1):
            print(f"{i}. {id_} | {pr} | {tit} | depende: {dep or '-'}")
        return 0
    filtro = argv[0] if argv else ""
    for m, bloco in blocos(texto, c["PREFIXO"]):
        st = campo(bloco, "Status")
        if filtro and not st.startswith(filtro):
            continue
        print(f"{m.group(1)} | {st} | {campo(bloco, 'Responsável') or '-'} | {campo(bloco, 'Depende de') or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
