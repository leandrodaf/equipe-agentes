#!/usr/bin/env python3
"""Configuração da equipe: acha o projeto e lê `.equipe/config.env`. Fonte única para os scripts
shell (`config.py shell`, usado pelo lib/comum.sh) e para os módulos Python (`config.carregar()`).

O projeto é a árvore principal do repositório git que tem `.equipe/config.env`:
  1. a variável EQUIPE_RAIZ, se definida;
  2. senão, a árvore principal do repositório do diretório atual (vale também de dentro de uma
     worktree: os agentes trabalham nelas, mas o estado da equipe fica na principal);
  3. senão, o primeiro diretório acima do atual com `.equipe/config.env`.

    config.py shell     → KEY='valor' de toda a configuração (para `eval` no shell)
    config.py ver       → a configuração efetiva, legível
    config.py raiz      → só o caminho do projeto
"""
import os
import re
import shlex
import subprocess
import sys

EQUIPE_HOME = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Tudo o que pode ir no .equipe/config.env, com o valor padrão. O modelo comentado está em
# modelos/config.env; a explicação de cada chave, no README.
PADRAO = {
    "PROJETO": "",  # padrão: o nome da pasta do projeto
    "DESCRICAO": "",
    "RAMO": "main",
    "FILA": "MELHORIAS.md",
    "ARQUIVO_FILA": "MELHORIAS-ARQUIVO.md",
    "PREFIXO": "MEL",
    "CHANGELOG": "CHANGELOG.md",
    "LIMITE_VIVOS": "20",
    "GATE": "make verificar",
    "INSTALAR": "",
    "TESTE_RAPIDO": "",
    "PUSH": "1",
    "APP_URL": "",
    "APP_ATIVO": "",
    "APP_SUBIR": "",
    "APP_PARAR": "",
    "PORTAS_DONO": "",
    "PORTAS_ANALISTA": "8090-8099",
    "PORTAS_IMPLEMENTADOR": "8100-8199",
    "PAINEL_PORTA": "8077",
    "PAINEL_IP_EXTRA": "",
    "EVIDENCIAS": "docs/evidencias",
    "VALIDACAO_REGEX": r"make (-s )?(verificar|test|check)|go test|vitest|jest|pytest|cargo test|golangci-lint|eslint|pnpm (e2e|test|lint)|npm (run )?test",
    "CLAUDE_ARGS": "",
    "CODEX_ARGS": "",
    "DEEP_COMANDO": "claude-deep",
    "N_CLAUDE": "3",  # quantos de cada o `equipe subir` mantém (o supervisor segue isso)
    "N_CODEX": "3",
    "N_DEEP": "0",
    "TERMINAL_AGENTES": "",  # vazio: gnome-terminal se houver tela; "tmux": só a sessão tmux
}

# Chaves que a variável de ambiente de mesmo nome sobrepõe (uma execução só, sem editar o config):
# ex.: o supervisor abre agentes com TERMINAL_AGENTES=tmux; `CLAUDE_ARGS="--model haiku" equipe agentes 1 0`.
DO_AMBIENTE = ("TERMINAL_AGENTES", "CLAUDE_ARGS", "CODEX_ARGS", "DEEP_COMANDO", "N_CLAUDE", "N_CODEX", "N_DEEP", "PAINEL_PORTA")

LINHA = re.compile(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)=(.*)$")


class SemProjeto(Exception):
    pass


def _tem_config(d):
    return os.path.isfile(os.path.join(d, ".equipe", "config.env"))


def achar_raiz(inicio=None):
    if os.environ.get("EQUIPE_RAIZ"):
        return os.path.abspath(os.environ["EQUIPE_RAIZ"])
    inicio = os.path.abspath(inicio or os.getcwd())
    try:
        comum = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=inicio,
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        comum = ""
    if comum and os.path.basename(comum) == ".git" and _tem_config(os.path.dirname(comum)):
        return os.path.dirname(comum)
    d = inicio
    while True:
        if _tem_config(d):
            return d
        pai = os.path.dirname(d)
        if pai == d:
            raise SemProjeto("nenhum projeto da equipe aqui: rode `equipe iniciar` na raiz do repositório (ou defina EQUIPE_RAIZ)")
        d = pai


def ler_env(caminho):
    """KEY=valor por linha, com aspas e comentário como no shell (o arquivo também é lido pelo bash)."""
    out = {}
    try:
        with open(caminho, encoding="utf-8") as f:
            linhas = f.read().splitlines()
    except OSError:
        return out
    for l in linhas:
        m = LINHA.match(l)
        if not m:
            continue
        try:
            partes = shlex.split(m.group(2), comments=True)
        except ValueError:
            partes = [m.group(2).strip()]
        out[m.group(1)] = " ".join(partes)
    return out


def pasta_sessoes_claude(raiz):
    """O Claude Code guarda as sessões em ~/.claude/projects/<caminho com tudo que não é letra/número trocado por ->."""
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", raiz))


def carregar(raiz=None, exigir=True):
    try:
        raiz = os.path.abspath(raiz) if raiz else achar_raiz()
    except SemProjeto:
        if exigir:
            raise
        raiz = os.path.abspath(os.environ.get("EQUIPE_RAIZ") or os.getcwd())
    c = dict(PADRAO)
    c.update(ler_env(os.path.join(raiz, ".equipe", "config.env")))
    c.update({k: os.environ[k] for k in DO_AMBIENTE if os.environ.get(k)})
    c["PROJETO"] = re.sub(r"[^A-Za-z0-9_-]", "-", c["PROJETO"] or os.path.basename(raiz)) or "projeto"
    c["PREFIXO"] = re.sub(r"[^A-Za-z0-9]", "", c["PREFIXO"]).upper() or "MEL"
    c.update(
        RAIZ=raiz,
        EQUIPE_HOME=EQUIPE_HOME,
        PASTA=os.path.join(raiz, ".equipe"),
        ESTADO=os.path.join(raiz, ".equipe", "estado"),
        SESSAO_TMUX="equipe-" + c["PROJETO"],
        PREFIXO_MIN=c["PREFIXO"].lower(),
        SESSOES_CLAUDE=pasta_sessoes_claude(raiz),
    )
    return c


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "ver"
    try:
        c = carregar()
    except SemProjeto as e:
        print(f"equipe: {e}", file=sys.stderr)
        return 2
    if cmd == "shell":
        for k, v in c.items():
            print(f"{k}={shlex.quote(str(v))}")
    elif cmd == "raiz":
        print(c["RAIZ"])
    elif cmd == "ver":
        for k in sorted(c):
            print(f"{k}={c[k]}")
    else:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
