#!/usr/bin/env python3
"""Imprime um roteiro com os valores do projeto preenchidos.

    roteiro.py <nome>     (faxina | varredura | pesquisa | qualquer outro em .equipe/roteiros/)

O do projeto (`.equipe/roteiros/<nome>.md`) substitui o padrão (`roteiros/<nome>.md` do motor).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import prompt  # noqa: E402


def main(argv):
    if len(argv) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    c = config.carregar()
    nome = argv[0].removesuffix(".md")
    for caminho in (os.path.join(c["PASTA"], "roteiros", f"{nome}.md"), os.path.join(c["EQUIPE_HOME"], "roteiros", f"{nome}.md")):
        if os.path.isfile(caminho):
            with open(caminho, encoding="utf-8") as f:
                texto = f.read()
            sys.stdout.write(prompt.preencher(texto, prompt.valores(c, os.environ.get("AGENTE", "analista")), caminho))
            return 0
    print(f"roteiro não encontrado: {nome}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
