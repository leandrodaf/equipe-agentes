#!/usr/bin/env python3
"""Monta o prompt de abertura de um agente: cabeçalho de identidade + protocolo genérico do papel
(prompts/<papel>.md, com os {{VALORES}} do .equipe/config.env) + o contexto do projeto.

    prompt.py <papel> <nome>      papel = analista | implementador | caminho de um modelo (testes)

O contexto do projeto vem de `.equipe/projeto.md` (todos os agentes) e `.equipe/<papel>.md`
(só aquele papel), ambos opcionais. O cabeçalho é o que identifica o agente (lib/identidade.py):

    # Equipe <projeto> · papel: <papel>
    SEU NOME: <nome>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

MARCA = re.compile(r"\{\{([A-Z_]+)\}\}")


def valores(c, nome):
    v = {k: str(x) for k, x in c.items()}
    v["NOME"] = nome
    v["ESTADO_REL"] = os.path.relpath(c["ESTADO"], c["RAIZ"])
    # Valores opcionais vazios viram um texto que se lê bem no meio da frase.
    for k, vazio in (("INSTALAR", "nenhum: o projeto não precisa"), ("TESTE_RAPIDO", "o teste do arquivo ou pacote que você mexeu"),
                     ("APP_URL", "nenhum app do dono configurado"), ("PORTAS_DONO", "nenhuma"), ("DESCRICAO", "veja o .equipe/projeto.md")):
        if not v.get(k):
            v[k] = vazio
    return v


def preencher(texto, v, origem):
    faltam = sorted({m for m in MARCA.findall(texto) if m not in v})
    if faltam:
        raise SystemExit(f"{origem}: valor desconhecido {', '.join('{{' + f + '}}' for f in faltam)}")
    return MARCA.sub(lambda m: v[m.group(1)], texto)


def ler(caminho):
    """Texto do arquivo sem os comentários HTML (as instruções dos modelos não vão para o prompt)."""
    try:
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
    except OSError:
        return ""
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"<!--.*?-->", "", texto, flags=re.S)).strip()


def montar(papel, nome, c=None):
    c = c or config.carregar()
    v = valores(c, nome)
    if os.path.isfile(papel):
        modelo, papel = papel, os.path.splitext(os.path.basename(papel))[0]
    else:
        modelo = os.path.join(c["EQUIPE_HOME"], "prompts", f"{papel}.md")
    base = ler(modelo)
    if not base:
        raise SystemExit(f"modelo de prompt não encontrado: {modelo}")
    partes = [f"# Equipe {c['PROJETO']} · papel: {papel}", f"SEU NOME: {nome}", "", preencher(base, v, modelo)]
    projeto = ler(os.path.join(c["PASTA"], "projeto.md"))
    if projeto:
        partes += ["", "---", "", "# O projeto (`.equipe/projeto.md`: vale mais do que o genérico acima quando os dois divergem)", "",
                   preencher(projeto, v, ".equipe/projeto.md")]
    extra = ler(os.path.join(c["PASTA"], f"{papel}.md"))
    if extra:
        partes += ["", "---", "", f"# Só para o seu papel (`.equipe/{papel}.md`)", "", preencher(extra, v, f".equipe/{papel}.md")]
    return "\n".join(partes) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    sys.stdout.write(montar(sys.argv[1], sys.argv[2]))
