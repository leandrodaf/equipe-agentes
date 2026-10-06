#!/usr/bin/env python3
"""Prepara o repositório git atual para a equipe de agentes. Nunca sobrescreve o que já existe.

    equipe iniciar [--nome N] [--descricao "…"]

Cria, na raiz do repositório (a árvore principal, mesmo se rodado de uma worktree):
  .equipe/config.env   configuração (a partir de modelos/config.env)
  .equipe/projeto.md   contexto do projeto para os agentes (preencha!)
  <FILA>               a fila com o Protocolo, se ainda não existir
e põe `.equipe/estado/` no .git/info/exclude (estado local: diários, travas, mensagens).
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import prompt  # noqa: E402


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).stdout.strip()


def main(argv):
    ap = argparse.ArgumentParser(prog="equipe iniciar", description="Prepara o repositório atual para a equipe.")
    ap.add_argument("--nome", help="nome curto do projeto (padrão: o nome da pasta)")
    ap.add_argument("--descricao", default="", help="uma frase sobre o projeto")
    a = ap.parse_args(argv)

    comum = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if not comum or os.path.basename(comum) != ".git":
        print("rode dentro de um repositório git (com uma árvore principal normal)", file=sys.stderr)
        return 2
    raiz = os.path.dirname(comum)
    pasta = os.path.join(raiz, ".equipe")
    os.makedirs(os.path.join(pasta, "estado"), exist_ok=True)
    modelos = os.path.join(config.EQUIPE_HOME, "modelos")
    nome = re.sub(r"[^A-Za-z0-9_-]", "-", a.nome or os.path.basename(raiz))
    ramo = git("symbolic-ref", "--short", "HEAD", cwd=raiz) or "main"
    feitos = []

    cfg = os.path.join(pasta, "config.env")
    if not os.path.exists(cfg):
        texto = open(os.path.join(modelos, "config.env"), encoding="utf-8").read()
        texto = texto.replace("{{PROJETO}}", nome).replace("{{DESCRICAO}}", a.descricao.replace('"', "'")).replace("{{RAMO}}", ramo)
        open(cfg, "w", encoding="utf-8").write(texto)
        feitos.append(f"criado  .equipe/config.env (projeto {nome}, ramo {ramo})")
    else:
        feitos.append("mantido .equipe/config.env (já existia)")

    proj = os.path.join(pasta, "projeto.md")
    if not os.path.exists(proj):
        open(proj, "w", encoding="utf-8").write(open(os.path.join(modelos, "projeto.md"), encoding="utf-8").read())
        feitos.append("criado  .equipe/projeto.md (preencha: é o que os agentes sabem do projeto)")
    else:
        feitos.append("mantido .equipe/projeto.md")

    c = config.carregar(raiz)
    fila = os.path.join(raiz, c["FILA"])
    if not os.path.exists(fila):
        modelo = open(os.path.join(modelos, "FILA.md"), encoding="utf-8").read()
        open(fila, "w", encoding="utf-8").write(prompt.preencher(modelo, prompt.valores(c, "analista"), "modelos/FILA.md"))
        feitos.append(f"criado  {c['FILA']} (a fila, com o Protocolo)")
    else:
        feitos.append(f"mantido {c['FILA']}")

    exclude = os.path.join(comum, "info", "exclude")
    os.makedirs(os.path.dirname(exclude), exist_ok=True)
    atual = open(exclude, encoding="utf-8").read() if os.path.exists(exclude) else ""
    if ".equipe/estado/" not in atual.split():
        with open(exclude, "a", encoding="utf-8") as f:
            f.write(("" if atual.endswith("\n") or not atual else "\n") + "# equipe-agentes: estado local da equipe\n.equipe/estado/\n")
        feitos.append("ignorado .equipe/estado/ (em .git/info/exclude)")

    print("\n".join(feitos))
    print(f"""
Próximos passos:
  1. edite .equipe/config.env (GATE, INSTALAR, portas, app do dono) e .equipe/projeto.md
  2. confira o prompt montado:  equipe prompt implementador
  3. suba a equipe:             equipe subir N_CLAUDE=2 N_CODEX=0
  4. acompanhe:                 http://127.0.0.1:{c['PAINEL_PORTA']}""")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
