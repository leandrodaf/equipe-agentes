#!/usr/bin/env python3
"""Painel da equipe de agentes: tarefas, o que cada agente está fazendo e o console dele.

    equipe painel               → http://127.0.0.1:<PAINEL_PORTA> (padrão 8077)
    python3 painel/servidor.py [porta]

Só lê arquivos (a fila, diários, sessões do Claude/Codex, git). As ações são as mesmas dos
scripts: mandar mensagem (equipe msg), pausar/retomar (equipe pausar), ordem e prioridade da fila.
Escuta em 127.0.0.1 e, se PAINEL_IP_EXTRA estiver no config e existir na máquina (um IP privado
levado por um túnel até o celular, por exemplo), também nele. Nesse IP só aceita conexão vinda da
própria máquina (o processo do túnel): alguém na rede local que tente rotear até aqui é recusado.
"""

import glob
import hashlib
import json
import mimetypes
import shutil
import os
import re
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit, quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
sys.path.insert(0, LIB)
import config  # noqa: E402  (lib/config.py: o projeto e o .equipe/config.env)
import identidade  # noqa: E402  (lib/identidade.py: quem é agente da equipe)
import limites  # noqa: E402  (lib/limites.py: quanto resta do Claude e do Codex)

CFG = config.carregar(exigir=False)
RAIZ = CFG["RAIZ"]
ESTADO = CFG["ESTADO"]
MELHORIAS = os.path.join(RAIZ, CFG["FILA"])
PREFIXO = CFG["PREFIXO"]
ID = re.compile(rf"{re.escape(PREFIXO)}-\d+")
RAMO = CFG["RAMO"]
HOME = os.path.expanduser("~")
SESSOES_CLAUDE = CFG["SESSOES_CLAUDE"]
SESSOES_CODEX = os.path.join(HOME, ".codex", "sessions")
IP_PRIVADO = CFG["PAINEL_IP_EXTRA"]
LOCAIS = ("127.0.0.1",) + ((IP_PRIVADO,) if IP_PRIVADO else ())
EVIDENCIAS = os.path.join(RAIZ, CFG["EVIDENCIAS"]) if CFG["EVIDENCIAS"] else None
NOME_AGENTE = re.compile(r"^(claude|codex|deep)-\d+$|^analista$")


def rodar(*cmd, timeout=20):
    try:
        r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception as e:  # noqa: BLE001 - painel nunca cai por causa de um comando
        return f"(erro: {e})"


def cauda(caminho, n_bytes=400_000):
    """Últimas linhas de um arquivo grande sem ler tudo."""
    try:
        with open(caminho, "rb") as f:
            f.seek(0, 2)
            tam = f.tell()
            f.seek(max(0, tam - n_bytes))
            dados = f.read().decode("utf-8", "replace")
        linhas = dados.splitlines()
        return linhas[1:] if tam > n_bytes else linhas
    except OSError:
        return []


# ---------- itens da fila


def itens():
    try:
        texto = open(MELHORIAS, encoding="utf-8").read()
    except OSError:
        return []
    out = []
    for bloco in re.split(r"^(?=## )", texto, flags=re.M):
        m = re.match(rf"## ({re.escape(PREFIXO)}-\d+) · (.*)", bloco)
        if not m:
            continue

        def campo(nome):
            c = re.search(rf"^- {nome}:\s*(.*)$", bloco, re.M)
            return c.group(1).strip() if c else ""

        status = campo("Status")
        prio = re.search(r"P[0-3]", campo("Prioridade"))
        registro = [l for l in bloco.splitlines() if re.match(r"- 20\d\d-\d\d-\d\d \d\d:\d\d · ", l)]
        ultimo = max(registro, key=lambda l: l[2:18]) if registro else ""
        out.append(
            {
                "id": m.group(1),
                "titulo": m.group(2).strip(),
                "status": re.sub(r"\s*\(.*", "", status).strip(),
                "status_nota": status,
                "responsavel": campo("Responsável") or "",
                "prioridade": prio.group(0) if prio else "",
                "ultimo_registro": ultimo[2:400],
            }
        )
    return out


def entregues(n=8):
    """Os últimos itens que entraram na main e foram arquivados (seção Concluídos)."""
    try:
        texto = open(MELHORIAS, encoding="utf-8").read()
    except OSError:
        return []
    m = re.search(r"^## Concluídos.*?(?=^## |\Z)", texto, re.S | re.M)
    out = []
    for pos, l in enumerate(re.findall(rf"^- ({re.escape(PREFIXO)}-\d+) · (.*)$", m.group(0) if m else "", re.M)):
        id_, resto = l
        r = re.match(r"(.*) — APROVADO \(integrado em ([^,]+), (\d{4}-\d\d-\d\d)\)", resto)
        if r:
            out.append({"id": id_, "titulo": r.group(1).strip(), "hash": r.group(2).strip(), "data": r.group(3), "pos": pos})
    out.sort(key=lambda x: (x["data"], x["pos"]), reverse=True)
    return out[:n]


# ---------- sessões (console)


def primeiro_nome(caminho):
    """Identifica só pelo prompt de abertura da sessão (regra única em lib/identidade.py)."""
    return identidade.nome_da_sessao(caminho)


_cache_sessoes = {"t": 0, "mapa": {}}


def sessoes():
    """nome → (ferramenta, arquivo) da sessão mais recente de cada agente."""
    if time.time() - _cache_sessoes["t"] < 15:
        return _cache_sessoes["mapa"]
    arquivos = [("claude", f) for f in glob.glob(os.path.join(SESSOES_CLAUDE, "*.jsonl"))]
    arquivos += [("codex", f) for f in glob.glob(os.path.join(SESSOES_CODEX, "*", "*", "*", "*.jsonl"))]
    arquivos = sorted(arquivos, key=lambda x: os.path.getmtime(x[1]), reverse=True)[:80]
    mapa = {}
    for ferr, f in arquivos:
        nome = primeiro_nome(f)
        if nome and nome not in mapa:
            mapa[nome] = (ferr, f)
    _cache_sessoes.update(t=time.time(), mapa=mapa)
    return mapa


def curto(s, n=220):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def curto_fim(s, n=400):
    """Como curto(), mas guarda o fim (onde ficam a conclusão e a pergunta)."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else "…" + s[-(n - 1):]


def hora(ts):
    return (ts or "")[11:16]


def console_claude(caminho, n, completo=False):
    ev = []
    for l in cauda(caminho, 2_000_000 if completo else 400_000):
        try:
            d = json.loads(l)
        except ValueError:
            continue
        t = d.get("timestamp", "")
        c = (d.get("message") or {}).get("content")
        if not isinstance(c, list):
            if d.get("type") == "user" and isinstance(c, str) and not c.startswith("<"):
                ev.append({"h": t, "tipo": "entrada", "txt": curto(c)})
            continue
        for it in c:
            tp = it.get("type")
            if tp == "text" and d.get("type") == "assistant":
                ev.append({"h": t, "tipo": "fala", "txt": (it.get("text") or "") if completo else curto_fim(it.get("text"))})
            elif tp == "tool_use":
                i = it.get("input") or {}
                alvo = i.get("command") or i.get("file_path") or i.get("pattern") or i.get("description") or i.get("url") or ""
                txt = f"$ {alvo}" if it.get("name") == "Bash" else f"{it.get('name')}: {alvo}"
                ev.append({"h": t, "tipo": "acao", "txt": curto(txt, 260)})
            elif tp == "tool_result" and it.get("is_error"):
                cont = it.get("content")
                txt = cont if isinstance(cont, str) else " ".join(x.get("text", "") for x in cont or [] if isinstance(x, dict))
                ev.append({"h": t, "tipo": "erro", "txt": curto(txt)})
            elif tp == "text" and d.get("type") == "user" and not it.get("text", "").startswith("<"):
                ev.append({"h": t, "tipo": "entrada", "txt": curto(it.get("text"))})
    return ev[-n:]


def console_codex(caminho, n, completo=False):
    ev = []
    for l in cauda(caminho, 2_000_000 if completo else 400_000):
        try:
            d = json.loads(l)
        except ValueError:
            continue
        t, p = d.get("timestamp", ""), d.get("payload") or {}
        tp = p.get("type")
        if d.get("type") == "response_item":
            if tp == "message" and p.get("role") == "assistant":
                txt = " ".join(x.get("text", "") for x in p.get("content") or [])
                ev.append({"h": t, "tipo": "fala", "txt": txt if completo else curto_fim(txt)})
            elif tp == "message" and p.get("role") == "user":
                txt = " ".join(x.get("text", "") for x in p.get("content") or [])
                if not txt.startswith("<"):
                    ev.append({"h": t, "tipo": "entrada", "txt": curto(txt)})
            elif tp in ("custom_tool_call", "function_call"):
                arg = str(p.get("input") or p.get("arguments") or "")
                cmd = re.search(r'cmd\s*:\s*"((?:[^"\\]|\\.)*)"', arg)
                txt = f"$ {cmd.group(1)}" if cmd else f"{p.get('name')}: {arg}"
                ev.append({"h": t, "tipo": "acao", "txt": curto(txt.replace('\\"', '"').replace("\\n", " "), 260)})
        elif d.get("type") == "event_msg" and tp == "turn_aborted":
            ev.append({"h": t, "tipo": "erro", "txt": f"interrompido ({p.get('reason', '')})"})
        elif d.get("type") == "event_msg" and tp == "task_complete":
            ev.append({"h": t, "tipo": "fim", "txt": "terminou a vez"})
    return ev[-n:]


def segundos_desde(iso):
    try:
        from datetime import datetime
        return int(time.time() - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return None


def pergunta_pendente(console, _seg=None):
    """Texto da pergunta se a última fala do agente pergunta algo e nada aconteceu há ≥ 60 s.
    (O Codex regrava o arquivo da sessão mesmo parado: conta o último evento, não o arquivo.)"""
    falas = [e for e in console if e["tipo"] in ("fala", "entrada", "acao")]
    if not falas or falas[-1]["tipo"] != "fala":
        return None
    parado = segundos_desde(console[-1]["h"])
    if parado is None or parado < 60:
        return None
    txt = falas[-1]["txt"].rstrip(" .…")
    return txt if "?" in txt[-300:] else None


def perguntas():
    """[(nome, pergunta)] dos implementadores parados esperando resposta."""
    out = []
    agora = time.time()
    for nome, (ferr, arq) in sessoes().items():
        if nome == "analista" or agora - os.path.getmtime(arq) > 6 * 3600:
            continue
        cons = (console_claude if ferr == "claude" else console_codex)(arq, 30)
        p = pergunta_pendente(cons)
        if p:
            out.append((nome, p))
    return out


# ---------- máquina

_cpu_antes = {"total": 0, "ocioso": 0}
VALIDACAO = re.compile(CFG["VALIDACAO_REGEX"])
GATE = CFG["GATE"]


def worktrees():
    """Caminhos das worktrees do projeto (sem a árvore principal)."""
    out = []
    for l in rodar("git", "worktree", "list", "--porcelain").splitlines():
        if l.startswith("worktree ") and l[9:] != RAIZ:
            out.append(l[9:])
    return out


def sistema():
    """CPU (desde a última leitura), memória e validações (testes/lint) rodando agora."""
    try:
        campos = [int(x) for x in open("/proc/stat").readline().split()[1:]]
        total, ocioso = sum(campos[:8]), campos[3] + campos[4]
        primeira = _cpu_antes["total"] == 0
        dt, di = total - _cpu_antes["total"], ocioso - _cpu_antes["ocioso"]
        _cpu_antes.update(total=total, ocioso=ocioso)
        cpu = None if primeira or dt <= 0 else round(100 * (dt - di) / dt)
    except OSError:
        cpu = None
    mem = {}
    try:
        for l in open("/proc/meminfo"):
            k, v = l.split(":")
            mem[k] = int(v.split()[0])
    except OSError:
        pass
    total_mb, livre_mb = mem.get("MemTotal", 0) // 1024, mem.get("MemAvailable", 0) // 1024
    # Validações: processos de teste/lint, agrupados pela worktree (ou "main").
    grupos = {}
    wts = worktrees()
    for d in glob.glob("/proc/[0-9]*"):
        try:
            cmd = open(d + "/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        exe = os.path.basename(cmd.split(" ", 1)[0])
        # As sessões dos agentes levam o prompt na linha de comando, que cita "make verificar".
        if exe in ("claude", "codex") or "SEU NOME:" in cmd or not VALIDACAO.search(cmd) or "--perguntas" in cmd:
            continue
        try:
            cwd = os.readlink(d + "/cwd")
        except OSError:
            cwd = ""
        wt = next((w for w in wts if (cwd + "/").startswith(w + "/")), None)
        onde = os.path.basename(wt) if wt else (RAMO if (cwd + "/").startswith(RAIZ + "/") else "outro")
        tipo = "gate completo" if GATE and GATE in cmd else "testes"
        grupos.setdefault(onde, set()).add(tipo)
    validacoes = [{"onde": k, "o_que": ", ".join(sorted(v))} for k, v in sorted(grupos.items())]
    return {
        "cpu": cpu,
        "nucleos": os.cpu_count(),
        "carga": round(os.getloadavg()[0], 1),
        "mem_usada_mb": total_mb - livre_mb,
        "mem_total_mb": total_mb,
        "validacoes": validacoes,
    }


def agentes_vivos():
    """Nomes com processo vivo agora: claude/codex aberto com o prompt do agente (lib/identidade.py)."""
    return {nome for _, nome in identidade.processos()}


# ---------- estado geral


def diario(nome, n=6):
    f = os.path.join(ESTADO, f"{nome}.md")
    linhas = [l for l in cauda(f, 60_000) if re.search(r"\d\d:\d\d", l)]
    return [curto(re.sub(r"^- ", "", l), 300) for l in linhas[-n:]]


def travas():
    out = {}
    for l in rodar(os.path.join(LIB, "trava.sh"), "ver").splitlines():
        m = re.match(r"(\w+): (\S+) (.*)", l)
        if m:
            out[m.group(1)] = {"quem": m.group(2), "desde": m.group(3)}
    return out


def estado(detalhe=None):
    agora = time.time()
    its = itens()
    por_id = {i["id"]: i for i in its}
    mapa = sessoes()
    # Sessão sem diário nem item (ex.: teste) só aparece enquanto está ativa.
    vivos = agentes_vivos()
    nomes = {n for n in mapa if n in vivos}
    for f in glob.glob(os.path.join(ESTADO, "*.md")):
        n = os.path.basename(f)[:-3]
        if NOME_AGENTE.match(n) and agora - os.path.getmtime(f) < 86400:
            nomes.add(n)
    for i in its:
        if i["responsavel"] and i["status"] not in ("DESCARTADO",):
            nomes.add(i["responsavel"])
    agentes = []
    for nome in sorted(nomes, key=lambda x: (x != "analista", x)):
        if not NOME_AGENTE.match(nome):
            continue
        ferr, arq = mapa.get(nome, (None, None))
        seg = int(agora - os.path.getmtime(arq)) if arq else None
        meus = [i["id"] for i in its if i["responsavel"] == nome]
        dia = diario(nome)
        atual = meus[0] if meus else ""
        for m in ID.findall(" ".join(dia[-1:])):
            if m in meus:
                atual = m
                break
        cons = []
        if arq:
            n_ev = 60 if detalhe in (nome, "todos") else 12
            cons = (console_claude if ferr == "claude" else console_codex)(arq, n_ev)
        ultimo = cons[-1] if cons else None
        if ultimo:
            sinal = segundos_desde(ultimo["h"])
            if sinal is not None:
                seg = sinal
        pergunta = pergunta_pendente(cons, seg) if nome != "analista" and nome in vivos else None
        # Sem processo vivo: fechado (ou interrompido). Com processo: trabalhando, perguntando ou esperando.
        if nome not in vivos:
            situacao = "interrompido" if ultimo and ultimo["tipo"] == "erro" and "interrompido" in ultimo["txt"] else "fechado"
        elif pergunta:
            situacao = "perguntando"
        elif seg is not None and seg < 120:
            situacao = "trabalhando"
        else:
            situacao = "esperando"
        agentes.append(
            {
                "nome": nome,
                "ferramenta": "deep" if nome.startswith("deep-") else ferr or ("codex" if nome.startswith("codex") else "claude"),
                "situacao": situacao,
                "ultimo_sinal_s": seg,
                "item": atual,
                "item_titulo": por_id.get(atual, {}).get("titulo", ""),
                "item_status": por_id.get(atual, {}).get("status", ""),
                "outros_itens": [m for m in meus if m != atual],
                "diario": dia,
                "console": cons,
                "pergunta": pergunta,
            }
        )
    commits = [
        dict(zip(("hash", "quando", "msg"), l.split("\t", 2)))
        for l in rodar("git", "log", "-12", "--date=format:%d/%m %H:%M", "--format=%h\t%cd\t%s", RAMO).splitlines()
        if l.count("\t") == 2
    ]
    wts = []
    for bloco in rodar("git", "worktree", "list", "--porcelain").split("\n\n"):
        cam = re.search(r"^worktree (.*)$", bloco, re.M)
        br = re.search(r"^branch refs/heads/(.*)$", bloco, re.M)
        if cam and cam.group(1) != RAIZ:
            wts.append({"caminho": os.path.basename(cam.group(1)), "branch": br.group(1) if br else "(solta)"})
    pausa = None
    pf = os.path.join(ESTADO, "PAUSA")
    if os.path.exists(pf):
        l = open(pf, encoding="utf-8").read().splitlines() + ["", ""]
        pausa = {"desde": l[0], "motivo": l[1]}
    msgs = [curto(l, 300) for l in cauda(os.path.join(ESTADO, "mensagens.log"), 30_000)[-12:]]
    return {
        "projeto": CFG["PROJETO"],
        "descricao": CFG["DESCRICAO"],
        "prefixo": PREFIXO,
        "fila": CFG["FILA"],
        "app_url": CFG["APP_URL"],
        "agora": time.strftime("%d/%m %H:%M:%S"),
        "sistema": sistema(),
        "pausa": pausa,
        "travas": travas(),
        "agentes": agentes,
        "itens": [i for i in its if i["status"] not in ("DESCARTADO",)],
        "ordem": ordem_do_dono(),
        "entregues": entregues(),
        "commits": commits,
        "worktrees": wts,
        "mensagens": msgs,
        "conversa": conversa_analista(mapa),
        "limites": limites_seguros(),
        "supervisor": supervisor_estado(),
    }


def supervisor_estado():
    """Se o supervisor está no ar, as últimas decisões e quem ele já despertou (lib/supervisor.py)."""
    try:
        pid = int(open(os.path.join(ESTADO, "supervisor.pid")).read().strip())
        os.kill(pid, 0)
        rodando = True
    except (OSError, ValueError):
        rodando = False
    try:
        memoria = json.load(open(os.path.join(ESTADO, "supervisor-estado.json"), encoding="utf-8"))
    except (OSError, ValueError):
        memoria = {}
    return {
        "rodando": rodando,
        "log": [curto(l, 300) for l in cauda(os.path.join(ESTADO, "supervisor.log"), 20_000)[-8:]],
        "despertados": {n: c.get("n", 0) for n, c in (memoria.get("cutucadas") or {}).items()},
    }


def limites_seguros():
    try:
        return limites.resumo(esperar=False)
    except Exception as e:  # noqa: BLE001 - painel nunca cai por causa da leitura de limite
        return {"erro": str(e)[:200]}


def mensagens_estruturadas():
    """Log de entrega, incluindo continuações de mensagens com várias linhas."""
    eventos = []
    padrao = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d) · (\S+) → (\S+) \(([^)]+)\) · (.*)$")
    for linha in cauda(os.path.join(ESTADO, "mensagens.log"), 200_000):
        m = padrao.match(linha)
        if m:
            h, de, para, via, texto = m.groups()
            eventos.append({"h": h.replace(" ", "T"), "de": de, "para": para, "via": via, "txt": texto})
        elif eventos:
            eventos[-1]["txt"] += "\n" + linha
    return eventos


def conversa_analista(mapa):
    """Falas completas e entregas do dono; prompts e ferramentas ficam na atividade."""
    eventos = []
    ferr, arquivo = mapa.get("analista", (None, None))
    if arquivo:
        leitor = console_claude if ferr == "claude" else console_codex
        for ev in leitor(arquivo, 500, completo=True):
            if ev["tipo"] == "fala" and ev["txt"].strip():
                eventos.append(dict(ev, de="analista", via="sessão"))
    for ev in mensagens_estruturadas():
        if ev["de"] == "dono" and ev["para"] == "analista":
            eventos.append(dict(ev, tipo="entrada"))
        elif ev["de"] == "analista" and ev["para"] == "dono":
            # A fala na sessão já representa a mesma resposta, quando presente.
            if not any(e["txt"] == ev["txt"] for e in eventos):
                eventos.append(dict(ev, tipo="fala"))
    # Horários de sessões têm timezone; o log usa o horário local da máquina.
    from datetime import datetime
    def timestamp(ev):
        try:
            return datetime.fromisoformat(ev["h"].replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            return 0
    eventos.sort(key=timestamp)
    ocorrencias = {}
    for ev in eventos:
        chave = hashlib.sha256((ev["h"] + ev["de"] + ev["txt"]).encode()).hexdigest()[:20]
        ocorrencias[chave] = ocorrencias.get(chave, 0) + 1
        ev["id"] = f"{chave}-{ocorrencias[chave]}"
    return eventos[-200:]


EXTENSOES_ARTEFATO = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".md", ".txt", ".log", ".json", ".html", ".pdf", ".csv", ".zip", ".mp4", ".webm", ".sh"}
_cache_artefatos = {"t": 0, "arquivos": []}


def caminho_artefato(relativo):
    """Somente arquivos dos dois acervos autorizados, inclusive depois de resolver symlinks."""
    if not relativo or os.path.isabs(relativo):
        return None
    caminho = os.path.realpath(os.path.join(RAIZ, relativo))
    raizes = [os.path.realpath(ESTADO)] + ([os.path.realpath(EVIDENCIAS)] if EVIDENCIAS else [])
    if not any(os.path.commonpath([r, caminho]) == r for r in raizes):
        return None
    if os.path.splitext(caminho)[1].lower() not in EXTENSOES_ARTEFATO or not os.path.isfile(caminho):
        return None
    return caminho


def artefatos():
    if time.time() - _cache_artefatos["t"] < 20:
        return _cache_artefatos["arquivos"]
    arquivos = []
    for raiz in [ESTADO] + ([EVIDENCIAS] if EVIDENCIAS else []):
        for pasta, diretorios, nomes in os.walk(raiz, followlinks=False):
            diretorios[:] = [d for d in diretorios if not d.startswith(".")]
            for nome in nomes:
                if nome.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(pasta, nome), RAIZ)
                caminho = caminho_artefato(rel)
                if not caminho:
                    continue
                try:
                    stat = os.stat(caminho)
                    ext = os.path.splitext(nome)[1].lower()
                    tipo = "imagem" if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"} else "relatorio" if ext in {".md", ".html", ".pdf"} else "video" if ext in {".mp4", ".webm"} else "dados" if ext in {".json", ".csv"} else "log" if ext in {".log", ".txt"} else "arquivo"
                    interno = any(p in rel.split("/") for p in ("prompts", "caixa", "verificacoes", "parada", "backups")) or (pasta == ESTADO and (NOME_AGENTE.fullmatch(os.path.splitext(nome)[0]) is not None or nome in {"painel.log", "mensagens.log", "ordem.json", "recuperacao.log"}))
                    vinculos = sorted(set(f"{PREFIXO}-" + m for m in re.findall(rf"{re.escape(PREFIXO)}[-_](\d+)", rel, re.I)))
                    if not interno and not vinculos and ext in {".md", ".html"} and stat.st_size < 200_000:
                        with open(caminho, encoding="utf-8", errors="replace") as f:
                            vinculos = sorted(set(ID.findall(f.read())))
                    arquivos.append({"caminho": rel, "nome": nome, "pasta": os.path.relpath(pasta, raiz), "tipo": tipo, "ext": ext, "bytes": stat.st_size, "modificado": stat.st_mtime, "itens": vinculos, "interno": interno})
                except OSError:
                    continue
    arquivos.sort(key=lambda a: a["modificado"], reverse=True)
    _cache_artefatos.update(t=time.time(), arquivos=arquivos)
    return arquivos


class Transmissao:
    """Uma coleta compartilhada para todos os navegadores conectados."""
    def __init__(self):
        self.condicao = threading.Condition()
        self.versao = 0
        self.corpo = None
        self.iniciada = False

    def iniciar(self):
        with self.condicao:
            if not self.iniciada:
                self.iniciada = True
                threading.Thread(target=self.coletar, daemon=True).start()

    def coletar(self):
        while True:
            try:
                corpo = json.dumps(estado("todos"), ensure_ascii=False)
                with self.condicao:
                    self.corpo = corpo
                    self.versao += 1
                    self.condicao.notify_all()
            except Exception:  # Uma leitura transitória não encerra a transmissão.
                pass
            time.sleep(2)


transmissao = Transmissao()


class Servidor(ThreadingHTTPServer):
    def verify_request(self, request, client_address):
        # Só a própria máquina: o navegador local e o processo do túnel (que conecta a partir do IP extra).
        return client_address[0] in LOCAIS


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _json(self, obj, code=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/api/artefatos":
            return self._json({"arquivos": artefatos()})
        if url.path in ("/api/arquivo", "/api/previa"):
            params = parse_qs(url.query)
            caminho = caminho_artefato(params.get("arquivo", [""])[0])
            if caminho is None:
                return self._json({"erro": "arquivo não encontrado"}, 404)
            if url.path == "/api/previa":
                with open(caminho, "rb") as f:
                    dados = f.read(512_001)
                return self._json({"texto": dados[:512_000].decode("utf-8", "replace"), "truncado": len(dados) > 512_000})
            tipo = mimetypes.guess_type(caminho)[0] or "application/octet-stream"
            if caminho.endswith((".md", ".log", ".sh")):
                tipo = "text/plain; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(os.path.getsize(caminho)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'")
            modo = "attachment" if params.get("download") == ["1"] else "inline"
            self.send_header("Content-Disposition", f"{modo}; filename*=UTF-8''{quote(os.path.basename(caminho))}")
            self.end_headers()
            try:
                with open(caminho, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if self.path == "/api/eventos":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            transmissao.iniciar()
            versao = -1
            try:
                self.wfile.write(b"retry: 2000\n\n")
                self.wfile.flush()
                while True:
                    with transmissao.condicao:
                        transmissao.condicao.wait_for(lambda: transmissao.versao != versao, timeout=15)
                        atual, corpo = transmissao.versao, transmissao.corpo
                    if corpo is not None and atual != versao:
                        self.wfile.write(f"id: {atual}\ndata: {corpo}\n\n".encode())
                        versao = atual
                    else:
                        self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
        if self.path.startswith("/api/estado"):
            m = re.search(r"detalhe=([\w-]+)", self.path)
            return self._json(estado(m.group(1) if m else None))
        if self.path in ("/", "/index.html"):
            import html
            corpo = open(os.path.join(os.path.dirname(__file__), "index.html"), encoding="utf-8").read()
            for chave, valor in (("PROJETO", CFG["PROJETO"]), ("INICIAL", CFG["PROJETO"][:1].lower() + "."), ("PREFIXO", PREFIXO)):
                corpo = corpo.replace("{{" + chave + "}}", html.escape(valor))
            corpo = corpo.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            return self.wfile.write(corpo)
        self.send_error(404)

    def do_POST(self):
        # Só aceita chamadas da própria página (mesma origem) para nada de fora acionar a equipe.
        origem = self.headers.get("Origin", "")
        hosts = "|".join(re.escape(h) for h in LOCAIS + ("localhost",))
        if origem and not re.match(rf"^http://({hosts}):\d+$", origem):
            return self._json({"erro": "origem recusada"}, 403)
        tam = int(self.headers.get("Content-Length") or 0)
        try:
            dados = json.loads(self.rfile.read(tam) or b"{}")
        except ValueError:
            return self._json({"erro": "json inválido"}, 400)
        env = dict(os.environ, AGENTE="dono")
        if self.path == "/api/mensagem":
            para, texto = str(dados.get("para", "")), str(dados.get("texto", "")).strip()
            if not (NOME_AGENTE.match(para) or para == "codex") or not texto:
                return self._json({"erro": "destino ou texto inválido"}, 400)
            if len(texto) > 20_000:
                return self._json({"erro": "mensagem muito longa (máximo 20.000 caracteres)"}, 400)
            try:
                r = subprocess.run([os.path.join(LIB, "msg.sh"), para, texto], cwd=RAIZ, env=env, capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                return self._json({"erro": "Tempo de entrega excedido. Confira o histórico antes de reenviar."}, 504)
            saida = (r.stdout + r.stderr).strip()
            via = "caixa" if "na caixa" in saida else "fila" if "na fila" in saida else "entregue"
            return self._json({"ok": r.returncode == 0, "saida": saida, "via": via}, 200 if r.returncode == 0 else 502)
        if self.path == "/api/pausa":
            acao = dados.get("acao")
            if acao not in ("pausar", "retomar"):
                return self._json({"erro": "ação inválida"}, 400)
            args = [os.path.join(LIB, "pausa.sh"), acao]
            if acao == "pausar":
                args.append(str(dados.get("motivo") or "pedido do dono (painel)"))
            r = subprocess.run(args, cwd=RAIZ, env=env, capture_output=True, text=True, timeout=300)
            return self._json({"ok": r.returncode == 0, "saida": (r.stdout + r.stderr).strip()})
        if self.path == "/api/ordem":
            ids = [i for i in dados.get("ids", []) if isinstance(i, str) and ID.fullmatch(i)]
            with open(ORDEM, "w", encoding="utf-8") as f:
                json.dump({"ids": ids, "atualizado": time.strftime("%Y-%m-%d %H:%M"), "por": "dono"}, f, ensure_ascii=False)
            return self._json({"ok": True, "saida": "ordem salva: " + " → ".join(ids[:6]) + (" …" if len(ids) > 6 else "")})
        if self.path == "/api/prioridade":
            ok, msg = mudar_prioridade(str(dados.get("id", "")), str(dados.get("p", "")))
            return self._json({"ok": ok, "saida": msg}, 200 if ok else 400)
        self.send_error(404)


ORDEM = os.path.join(ESTADO, "ordem.json")


def ordem_do_dono():
    try:
        return json.load(open(ORDEM, encoding="utf-8")).get("ids", [])
    except (OSError, ValueError):
        return []


def mudar_prioridade(item, nova):
    """Troca o P0–P3 da linha '- Prioridade:' do item, pela trava da fila, e registra."""
    if not ID.fullmatch(item) or nova not in ("P0", "P1", "P2", "P3"):
        return False, "item ou prioridade inválidos"
    trava = os.path.join(LIB, "trava.sh")
    r = subprocess.run([trava, "pegar", "fila", "dono"], cwd=RAIZ, capture_output=True, text=True, timeout=200)
    if not r.stdout.startswith("OK"):
        return False, f"{CFG['FILA']} ocupado por outro agente; tente de novo em instantes"
    try:
        texto = open(MELHORIAS, encoding="utf-8").read()
        m = re.search(rf"^## {item} · .*?(?=^## |\Z)", texto, re.S | re.M)
        if not m:
            return False, f"{item} não está no {CFG['FILA']}"
        bloco = m.group(0)
        linha = re.search(r"^- Prioridade:.*$", bloco, re.M)
        if not linha:
            return False, f"{item} sem linha de prioridade"
        antiga = re.search(r"P[0-3]", linha.group(0))
        if antiga and antiga.group(0) == nova:
            return True, f"{item} já é {nova}"
        nova_linha = re.sub(r"P[0-3]", nova, linha.group(0), count=1) if antiga else linha.group(0).replace("Prioridade:", f"Prioridade: {nova}", 1)
        bloco_novo = bloco.replace(linha.group(0), nova_linha, 1).rstrip("\n")
        bloco_novo += f"\n- {time.strftime('%Y-%m-%d %H:%M')} · dono · prioridade {antiga.group(0) if antiga else '-'} → {nova} (pelo painel)\n\n"
        with open(MELHORIAS, "w", encoding="utf-8") as f:
            f.write(texto[: m.start()] + bloco_novo + texto[m.end():])
        return True, f"{item}: prioridade {nova}"
    finally:
        subprocess.run([trava, "soltar", "fila", "dono"], cwd=RAIZ, capture_output=True, timeout=30)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--ultimo"]:  # usado pelo `equipe parar`: última ação de cada agente
        for nome in sys.argv[2:]:
            ferr, arq = sessoes().get(nome, (None, None))
            cons = (console_claude if ferr == "claude" else console_codex)(arq, 3) if arq else []
            ev = [e for e in cons if e["tipo"] in ("acao", "fala", "erro")]
            print(f"{nome}\t{curto(ev[-1]['txt'], 110) if ev else ''}")
        sys.exit(0)
    if sys.argv[1:2] == ["--perguntas"]:  # usado pelo monitor do analista
        for nome, p in perguntas():
            print(f"{nome}\t{p}")
        sys.exit(0)
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else int(CFG["PAINEL_PORTA"])
    print(f"painel da equipe ({CFG['PROJETO']}): http://127.0.0.1:{porta}")
    if IP_PRIVADO:
        try:  # só existe se o IP estiver na máquina (rede privada / túnel)
            privado = Servidor((IP_PRIVADO, porta), Handler)
            threading.Thread(target=privado.serve_forever, daemon=True).start()
            print(f"também em http://{IP_PRIVADO}:{porta}")
        except OSError:
            pass
    Servidor(("127.0.0.1", porta), Handler).serve_forever()
