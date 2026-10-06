#!/usr/bin/env python3
"""Quem é agente da equipe deste projeto: a única regra, usada por todos os scripts e pelo painel.

Um processo ou uma sessão só é o agente <nome> do projeto P se foi ABERTO com o prompt do agente
(o `equipe agentes` passa o prompt inteiro como argumento). O prompt começa assim:

    # Equipe P · papel: implementador
    SEU NOME: claude-2

  - analista: o papel começa com "analista";
  - claude-N / codex-N / deep-N: qualquer outro papel, com a linha "SEU NOME: <nome>" logo no começo;
  - ou o `-n <nome>@P` com que o abrir.sh lança o Claude.
E o processo tem de ser o próprio claude/codex. Assim nunca conta como agente: um Claude ou Codex
aberto para outra coisa (mesmo que leia, cite ou edite os prompts), um grep/sed/python com o texto
do prompt na linha de comando, o servidor do tmux, nem um agente de OUTRO projeto com o mesmo nome.

  identidade.py vivos            nomes dos agentes rodando agora (um por linha)
  identidade.py vivo <nome>      sai 0 se <nome> está rodando
  identidade.py pids <nome>      PIDs das sessões de <nome>
  identidade.py sessoes-codex    "nome uuid" das sessões Codex recentes (mais nova antes)
  identidade.py sessao <arquivo> nome do agente de um .jsonl de sessão (Claude ou Codex)
"""
import functools
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

NOME = re.compile(r"^(?:claude|codex|deep)-\d+$")
CABECALHO = re.compile(r"^# Equipe (\S+) · papel: (\S+)")
SEU_NOME = re.compile(r"^SEU NOME: ((?:claude|codex|deep)-\d+)\b", re.M)
FERRAMENTAS = ("claude", "codex")


@functools.lru_cache(maxsize=1)
def projeto():
    return config.carregar(exigir=False)["PROJETO"]


def nome_do_prompt(texto, proj=None):
    """Nome do agente se o texto É um prompt de agente deste projeto (começa pelo cabeçalho), senão None."""
    proj = proj or projeto()
    texto = (texto or "").lstrip()
    m = CABECALHO.match(texto)
    if not m or m.group(1) != proj:
        return None
    if m.group(2).startswith("analista"):
        return "analista"
    n = SEU_NOME.search(texto[:2000])
    return n.group(1) if n else None


def argumentos(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
    except OSError:
        return []


def nome_do_processo(pid, proj=None):
    proj = proj or projeto()
    args = argumentos(pid)
    if not args:
        return None
    exe = os.path.basename(args[0])
    if exe == "node" and len(args) > 1:  # codex/claude instalados via npm: node <bin> …
        exe, args = os.path.basename(args[1]), args[1:]
    if exe not in FERRAMENTAS:
        return None
    for i, a in enumerate(args[1:], 1):
        nome = nome_do_prompt(a, proj)
        if nome:
            return nome
        if a == "-n" and i + 1 < len(args):
            nome, _, de = args[i + 1].partition("@")
            if de == proj and (NOME.match(nome) or nome == "analista"):
                return nome
    return None


def processos(proj=None):
    """[(pid, nome)] das sessões de agente deste projeto rodando agora (nunca este processo)."""
    proj = proj or projeto()
    out = []
    for d in glob.glob("/proc/[0-9]*"):
        pid = int(os.path.basename(d))
        if pid == os.getpid():
            continue
        nome = nome_do_processo(pid, proj)
        if nome:
            out.append((pid, nome))
    return out


INJETADO = ("<", "# AGENTS.md instructions")  # contexto que o Claude/Codex põe antes do prompt


def primeiro_prompt(caminho):
    """Primeira mensagem de verdade do usuário num .jsonl de sessão (Claude ou Codex)."""
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            for i, linha in enumerate(f):
                if i > 400:
                    return None
                try:
                    d = json.loads(linha)
                except ValueError:
                    continue
                if d.get("type") == "user" and not d.get("isMeta"):
                    conteudo = (d.get("message") or {}).get("content", "")
                elif d.get("type") == "response_item" and (d.get("payload") or {}).get("role") == "user":
                    conteudo = d["payload"].get("content", "")
                else:
                    continue
                if isinstance(conteudo, list):
                    if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in conteudo):
                        continue
                    conteudo = "\n".join(x.get("text", "") for x in conteudo if isinstance(x, dict))
                texto = (conteudo or "").lstrip()
                if not texto or texto.startswith(INJETADO):
                    continue
                return texto
    except OSError:
        return None
    return None


def nome_da_sessao(caminho, proj=None):
    return nome_do_prompt(primeiro_prompt(caminho), proj)


def sessoes_codex(proj=None):
    arquivos = sorted(glob.glob(os.path.expanduser("~/.codex/sessions/*/*/*/*.jsonl")), key=os.path.getmtime, reverse=True)
    for f in arquivos[:80]:
        nome = nome_da_sessao(f, proj)
        uuid = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=\.jsonl$)", f)
        if nome and nome.startswith("codex-") and uuid:
            yield nome, uuid.group(0)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "vivos":
        print("\n".join(sorted({n for _, n in processos()})))
    elif cmd == "vivo" and len(argv) == 3:
        return 0 if any(n == argv[2] for _, n in processos()) else 1
    elif cmd == "pids" and len(argv) == 3:
        print("\n".join(str(p) for p, n in processos() if n == argv[2]))
    elif cmd == "sessoes-codex":
        for nome, uuid in sessoes_codex():
            print(nome, uuid)
    elif cmd == "sessao" and len(argv) == 3:
        nome = nome_da_sessao(argv[2])
        if not nome:
            return 1
        print(nome)
    else:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
