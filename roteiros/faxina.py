#!/usr/bin/env python3
"""Relatório da faxina (roteiros/faxina.md). SÓ LÊ: lista o que pode sair, por que, e o comando.

    equipe faxina          # relatório completo
    equipe faxina --curto  # só as linhas com algo a fazer

Limpeza que depende do projeto (cópias de banco, containers, caches) fica no .equipe/projeto.md:
este relatório cobre o que é comum a todo projeto (fila, worktrees, portas, prints, diários, backups).

Quem apaga é o analista, item por item, depois de ler o motivo. O script nunca apaga, para,
derruba nem edita nada; por isso pode rodar a qualquer hora, inclusive com a equipe trabalhando.
"""
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import config  # noqa: E402

CFG = config.carregar()
RAIZ = Path(CFG["RAIZ"])
ESTADO = Path(CFG["ESTADO"])
LIB = Path(CFG["EQUIPE_HOME"]) / "lib"
MELHORIAS = RAIZ / CFG["FILA"]
PREFIXO = CFG["PREFIXO"]
RAMO = CFG["RAMO"]
LIMITE = int(CFG["LIMITE_VIVOS"])
REL = os.path.relpath(ESTADO, RAIZ)


def faixas(texto):
    out = []
    for f in texto.split():
        a, _, b = f.partition("-")
        if a.isdigit():
            out.append((int(a), int(b or a)))
    return out
CURTO = "--curto" in sys.argv
agora = dt.datetime.now()


def sh(*cmd, entrada=None):
    r = subprocess.run(cmd, capture_output=True, text=True, input=entrada, cwd=RAIZ)
    return r.returncode, r.stdout.strip()


def secao(titulo):
    print(f"\n## {titulo}")


def ok(txt):
    if not CURTO:
        print(f"  ✔ {txt}")


def fazer(txt, cmd=None):
    print(f"  → {txt}")
    if cmd:
        print(f"      {cmd}")


def tamanho(p):
    _, out = sh("du", "-sh", str(p))
    return out.split()[0] if out else "?"


texto = MELHORIAS.read_text(encoding="utf-8")
vivos = set(re.findall(rf"^## ({PREFIXO}-\d+) ·", texto, re.M))


def vivo(agente):
    return sh(str(LIB / "vivo.sh"), agente)[0] == 0


PAUSA = (ESTADO / "PAUSA").exists()


def abandonado(agente, item):
    """Motivo para recolher o que é de `agente` no `item`, ou None. Item vivo com a equipe em
    pausa ou com o dono escrevendo no diário nas últimas 3 h nunca é abandonado: ele volta e
    continua dali (lição: não liberar logo depois de um reinício)."""
    if item and item not in vivos:
        return f"{item} arquivado"
    if agente in ("?", "analista") or PAUSA or vivo(agente):
        return None
    diario = ESTADO / f"{agente}.md"
    horas = (agora.timestamp() - diario.stat().st_mtime) / 3600 if diario.exists() else 99
    return f"{agente} parado, diário sem linha há {horas:.0f} h" if horas > 3 else None


def backups_md():
    """Só as pastas de backup da fila (AAAA-MM-DD-HHMM[sufixo]); outros arquivos ali são do dono."""
    return sorted(d for d in (ESTADO / "backups").glob("20*") if d.is_dir())


# --- 0. Pode fazer faxina agora? ------------------------------------------------------------
secao("0. Condições")
uptime_min = (agora - dt.datetime.fromisoformat(sh("uptime", "-s")[1])).total_seconds() / 60
if uptime_min < 30:
    fazer(f"máquina ligada há {uptime_min:.0f} min (< 30): só os passos 1, 4, 5 e 6; nada de porta ou worktree")
else:
    ok(f"máquina ligada há {uptime_min / 60:.1f} h")
# Só processos que não são shells nem as sessões dos agentes (que levam o texto do gate no prompt).
_, ps = sh("ps", "-eo", "comm=,args=")
gates = [l for l in ps.splitlines() if CFG["GATE"] and CFG["GATE"] in l
         and l.split(" ", 1)[0] not in ("bash", "zsh", "sh", "claude", "codex", "node")]
if gates:
    fazer(f"{len(gates)} gate(s) rodando: não suba ambiente nem rode a passada; o resto da faxina pode seguir")
else:
    ok("nenhum gate rodando")
carga = os.getloadavg()[0]
(fazer if carga > os.cpu_count() * 0.7 else ok)(f"carga {carga:.1f} em {os.cpu_count()} núcleos")

# --- 1. A fila ------------------------------------------------------------------------
secao(f"1. {CFG['FILA']} (todo agente lê este arquivo inteiro: cada linha a menos é token a menos)")
linhas = texto.count("\n")
(fazer if linhas > 700 else ok)(f"{linhas} linhas, {len(texto.encode()) // 1024} KB (meta: ≤ 700 linhas)")
_, tabela = sh("python3", str(LIB / "itens.py"))
n_vivos = sum(1 for l in tabela.splitlines() if "DESCARTADO" not in l and not re.search(r"APROVADO.*integrado", l))
(fazer if n_vivos > LIMITE else ok)(f"{n_vivos} itens vivos (limite {LIMITE})")
concl = re.search(r"^## Concluídos.*?\n(.*?)(?=^## )", texto, re.M | re.S)
if concl:
    n = len(re.findall(rf"^- {PREFIXO}-", concl.group(1), re.M))
    (fazer if n > 15 else ok)(f"Concluídos: {n} linhas na fila (deixe as 15 mais recentes; o resto vai para o índice do arquivo)")
ideias = re.search(r"^## Ideias ainda não detalhadas.*?\n(.*?)(?=^## )", texto, re.M | re.S)
if ideias:
    n = len([l for l in ideias.group(1).splitlines() if l.strip()])
    (fazer if n > 15 else ok)(f"Ideias ainda não detalhadas: {n} linhas (máx. 15): a ideia mais velha sem evidência sai primeiro")
# Rodada sem nenhum item logo abaixo dela: o contexto provavelmente já pode ir para o arquivo.
blocos = re.split(r"^(?=## )", texto, flags=re.M)
for i, b in enumerate(blocos):
    m = re.match(r"## (Rodada \d+[^\n]*)", b)
    if m and not (i + 1 < len(blocos) and blocos[i + 1].startswith(f"## {PREFIXO}-")):
        fazer(f"provável rodada encerrada (nenhum item logo abaixo): {m.group(1)[:70]}")
    if re.match(r"## .*(concluída|encerrad)", b, re.I):
        fazer(f"seção encerrada ainda no arquivo: {b.splitlines()[0][3:70]}")
for bloco in re.split(r"^(?=## )", texto, flags=re.M):
    m = re.match(rf"## ({PREFIXO}-\d+) ·", bloco)
    dep = re.search(r"^- Depende de:\s*(.*)$", bloco, re.M)
    mortos = [d for d in re.findall(rf"{PREFIXO}-\d+", dep.group(1)) if d not in vivos] if m and dep else []
    if mortos:
        fazer(f"{m.group(1)} depende de {', '.join(mortos)} (já arquivados): a dependência está cumprida, tire da linha")
# Concluídos: o hash tem de estar no ramo principal (é o que liga item ↔ commit).
fora = []
for item, h in re.findall(rf"^- ({PREFIXO}-\d+) · .*?integrado em ([0-9a-f]{{7,40}})", texto, re.M):
    if sh("git", "merge-base", "--is-ancestor", h, RAMO)[0] != 0:
        fora.append(f"{item} ({h})")
(fazer if fora else ok)(f"Concluídos com hash fora do {RAMO}: {', '.join(fora) or 'nenhum'}")
ultimo_backup = max(backups_md(), key=lambda d: d.stat().st_mtime, default=None)
if ultimo_backup:
    idade_h = (agora - dt.datetime.fromtimestamp(ultimo_backup.stat().st_mtime)).total_seconds() / 3600
    (fazer if idade_h > 24 else ok)(f"último backup há {idade_h:.0f} h ({ultimo_backup.name})")

# --- 2. Worktrees ---------------------------------------------------------------------------
secao("2. Worktrees e branches")
fazer("rode o limpador (ele decide o que apaga e explica o resto)", "equipe limpar-worktrees --apagar | tail -15")

# --- 3. Servidores esquecidos ---------------------------------------------------------------
secao(f"3. Servidores nas portas dos agentes ({CFG['PORTAS_IMPLEMENTADOR']} {CFG['PORTAS_ANALISTA']})")
F_IMPL, F_ANA = faixas(CFG["PORTAS_IMPLEMENTADOR"]), faixas(CFG["PORTAS_ANALISTA"])
DONO = {a for a, _ in faixas(CFG["PORTAS_DONO"])}
na = lambda p, fs: any(a <= p <= b for a, b in fs)  # noqa: E731
_, ss = sh("ss", "-ltnpH")
for l in ss.splitlines():
    m = re.search(r":(\d+)\s.*pid=(\d+)", l)
    if not m:
        continue
    porta, pid = int(m.group(1)), m.group(2)
    if porta in DONO or not (na(porta, F_IMPL) or na(porta, F_ANA)):
        continue
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        cwd = "?"
    # worktree no padrão <raiz>-<agente>-<número do item>
    wt = re.search(re.escape(str(RAIZ)) + r"-((?:claude|codex|deep)-\d+)?-?(\d+)?", cwd)
    agente = "analista" if na(porta, F_ANA) else (wt.group(1) if wt and wt.group(1) else "?")
    item = f"{PREFIXO}-{wt.group(2)}" if wt and wt.group(2) else "?"
    motivo = abandonado(agente, item if item != "?" else None)
    if motivo and uptime_min >= 30:
        fazer(f"porta {porta} ({cwd}): {motivo}", f"fuser -k {porta}/tcp")
    else:
        ok(f"porta {porta}: {agente}, {item} ({cwd})")

# --- 4. Prints ------------------------------------------------------------------------------
secao(f"4. Prints ({tamanho(ESTADO / 'prints')})")
for d in sorted((ESTADO / "prints").glob("*")):
    idade = (agora - dt.datetime.fromtimestamp(d.stat().st_mtime)).days
    if d.name.startswith(f"{PREFIXO}-") and d.name not in vivos:
        fazer(f"{d.name} arquivado ({tamanho(d)})", f"rm -r {REL}/prints/{d.name}")
    elif not d.name.startswith(f"{PREFIXO}-") and idade > 7:
        fazer(f"{d.name}: sem item, {idade} dias ({tamanho(d)})", f"rm -r {REL}/prints/{d.name}")

# --- 5. Diários e logs ----------------------------------------------------------------------
secao("5. Diários e logs")
for f in sorted(ESTADO.glob("*.md")):
    n = f.read_text(encoding="utf-8", errors="replace").count("\n")
    if n > 500:
        fazer(f"{f.name}: {n} linhas → mova as mais antigas para diarios-antigos/{f.stem}-{agora:%Y-%m}.md e deixe as últimas 100")
for nome in ("mensagens.log", "painel.log", "recuperacao.log"):
    f = ESTADO / nome
    if f.exists() and f.stat().st_size > 512 * 1024:
        fazer(f"{nome}: {f.stat().st_size // 1024} KB (> 512 KB) → guarde as últimas 2000 linhas")
for d in ("logs", "verificacoes", "varredura"):
    p = ESTADO / d
    velhos = [f for f in p.glob("*") if (agora - dt.datetime.fromtimestamp(f.stat().st_mtime)).days > 14] if p.exists() else []
    if velhos:
        fazer(f"{d}/: {len(velhos)} arquivo(s) com mais de 14 dias", f"find {REL}/{d} -maxdepth 1 -mtime +14 -delete")

# --- 6. Backups -----------------------------------------------------------------------------
# Retenção: tudo das últimas 48 h + o último de cada dia dos 30 dias anteriores. Assim um dia
# agitado (20 arquivamentos) não empurra para fora o backup de ontem.
backups = backups_md()
manter, por_dia = set(), {}
for b in backups:
    quando = dt.datetime.fromtimestamp(b.stat().st_mtime)
    if agora - quando < dt.timedelta(hours=48):
        manter.add(b)
    elif agora - quando < dt.timedelta(days=32):
        por_dia[quando.date()] = b
manter |= set(por_dia.values())
sobra = [b for b in backups if b not in manter]
secao(f"6. Backups ({len(backups)}, {tamanho(ESTADO / 'backups')})")
if sobra:
    fazer(f"{len(sobra)} fora da retenção (48 h inteiras + 1 por dia por 30 dias)",
          "rm -r " + " ".join(f"{REL}/backups/{b.name}" for b in sobra[:40]) + (" …" if len(sobra) > 40 else ""))
else:
    ok("dentro da retenção")

livre = shutil.disk_usage(RAIZ).free / 2**30
(fazer if livre < 10 else ok)(f"disco livre: {livre:.0f} GB")
