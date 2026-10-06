#!/usr/bin/env python3
"""Supervisor da equipe: mantém os agentes rodando o máximo de tempo possível dentro dos limites do Claude e do Codex.

    equipe supervisor plano       → o que faria agora (não mexe em nada)
    equipe supervisor uma-vez     → decide e executa uma vez
    equipe supervisor rodar       → em loop (o `equipe subir` sobe em segundo plano; `equipe parar` derruba)
    equipe supervisor ver         → configuração, se está rodando e as últimas decisões
    equipe supervisor config claude=2 codex=3 deep=1 analista=codex,claude ativo=1

A cada volta lê os limites (lib/limites.py) e quem está vivo (lib/identidade.py):
- ferramenta crítica (≥ 85%): a analista muda para a outra ferramenta, se ela estiver ok;
  os implementadores dela terminam o item atual sem pegar outro (regra do prompt, `limites.py pode-pegar`).
- ferramenta em `parar_em`% (95) ou esgotada: os implementadores dela param pelo lib/parar.sh
  (pausa, commit WIP, travas soltas, diário), só eles (PARAR_SO), o resto da equipe segue.
- ferramenta ok de novo (o reset passou): reabre os implementadores que faltam (lib/abrir.sh), que
  continuam do diário, e a analista volta para a ferramenta preferida.
Despertador: na mesma volta, olha a última atividade de cada agente vivo (o console da sessão, como o
painel). Quem terminou a vez e ficou parado (analista 15 min, implementador 25 min) recebe pelo msg.sh
um DESPERTADOR com o que fazer; quem ignora 3 seguidos tem a sessão reiniciada (continua do diário).
Não cutuca quem está no meio de um comando, nem quem está numa ferramenta esgotada. Implementador
parado com pergunta não é cutucado: a analista recebe a pergunta.
Com a PAUSA do dono (equipe parar / equipe pausar) não faz nada: quem para a equipe à mão é o dono.

Configuração em .equipe/estado/supervisor.json (criada na primeira volta):
    implementadores   quantos de cada ferramenta manter quando ela está ok
    primeiro          número do primeiro (equipe subir PRIMEIRO=4 → claude-4, claude-5…)
    analista          ordem de preferência da ferramenta da analista
    parar_em          % da pior janela em que os implementadores da ferramenta param
    intervalo_s       entre uma volta e outra
    espera_reabrir_s  depois de parar uma ferramenta, quanto esperar antes de reabri-la (evita vai e volta)
    despertar_*_min   parado há quanto tempo (vez terminada) para receber o DESPERTADOR
    reiniciar_apos    DESPERTADORES seguidos sem resposta até reiniciar a sessão
    ativo             false: só observa e registra o que faria
"""

import json
import os
import re
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import identidade  # noqa: E402
import limites  # noqa: E402

import config  # noqa: E402

CFG = config.carregar(exigir=False)
RAIZ = CFG["RAIZ"]
ESTADO = CFG["ESTADO"]
EQUIPE_HOME = CFG["EQUIPE_HOME"]
CONFIG = os.path.join(ESTADO, "supervisor.json")
MEMORIA = os.path.join(ESTADO, "supervisor-estado.json")
LOG = os.path.join(ESTADO, "supervisor.log")
PID = os.path.join(ESTADO, "supervisor.pid")
PAUSA = os.path.join(ESTADO, "PAUSA")
FERRAMENTAS = ("claude", "codex", "deep")
FERRAMENTAS_ANALISTA = ("claude", "codex")  # a DeepSeek fica para itens simples, nunca para a analista

PADRAO = {
    "ativo": True,
    "implementadores": {"claude": 3, "codex": 3, "deep": 1},
    "primeiro": 1,
    "analista": ["claude", "codex"],
    "parar_em": 95,
    "intervalo_s": 300,
    "espera_reabrir_s": 900,
    "despertar_analista_min": 15,
    "despertar_implementador_min": 25,
    "reiniciar_apos": 3,
}


def ler_json(caminho, padrao):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def gravar_json(caminho, dados):
    os.makedirs(ESTADO, exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def config():
    if not os.path.exists(CONFIG):
        gravar_json(CONFIG, PADRAO)
    return {**PADRAO, **ler_json(CONFIG, {})}


def registrar(txt):
    linha = f"{time.strftime('%Y-%m-%d %H:%M')} · {txt}"
    print(linha, flush=True)
    os.makedirs(ESTADO, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


# ---------- quem está rodando


def ferramenta_do_pid(pid):
    args = identidade.argumentos(pid)
    exe = os.path.basename(args[0]) if args else ""
    if exe == "node" and len(args) > 1:
        exe = os.path.basename(args[1])
    return exe if exe in FERRAMENTAS else None


def vivos():
    """nome → ferramenta de cada agente rodando agora."""
    out = {}
    for pid, nome in identidade.processos():
        # deep-N roda o próprio binário claude (com a URL da DeepSeek): vale o nome
        out[nome] = "deep" if nome.startswith("deep-") else ferramenta_do_pid(pid) or limites.ferramenta_do_agente(nome)
    return out


# ---------- decisão (pura: dá para testar sem abrir nada)


def pior_uso(r):
    return max((j["usado"] for j in r.get("janelas") or []), default=0)


def situacao(r, parar_em):
    """'cresce' (pode abrir agente), 'segue' (os que estão continuam), 'sai' (analista vai embora), 'para' (todos param)."""
    n = r.get("nivel", "desconhecido")
    if n == "esgotado" or pior_uso(r) >= parar_em:
        return "para"
    if n == "critico":
        return "sai"
    if n == "atencao":
        return "segue"
    return "cresce"  # ok ou sem leitura


def planejar(lim, vivos_agora, cfg, memoria, agora):
    """Lista de ações: ("parar", [nomes], motivo) e ("abrir", ferramenta, nome, motivo)."""
    acoes = []
    sit = {f: situacao(lim[f], cfg["parar_em"]) if f in lim else "cresce" for f in FERRAMENTAS}

    def motivo(f):
        r = lim[f]
        uso = r.get("saldo_txt") or f"{pior_uso(r):.0f}%"
        return f"{f} {r['nivel']} ({uso}{', libera ' + r['libera'] if r.get('libera') else ''})"

    # Implementadores
    for f in FERRAMENTAS:
        meus = sorted(n for n, ferr in vivos_agora.items() if n != "analista" and ferr == f)
        if sit[f] == "para":
            if meus:
                acoes.append(("parar", meus, motivo(f)))
            continue
        if sit[f] != "cresce":
            continue
        parou = (memoria.get("parou") or {}).get(f, 0)
        if agora - parou < cfg["espera_reabrir_s"]:
            continue
        primeiro = int(cfg.get("primeiro", 1))
        for i in range(primeiro, primeiro + int(cfg["implementadores"].get(f, 0))):
            nome = f"{f}-{i}"
            if nome not in vivos_agora:
                acoes.append(("abrir", f, nome, f"{f} ok de novo" if parou else f"{f} ok"))

    # Analista: uma só, na primeira ferramenta da preferência que aguenta.
    atual = vivos_agora.get("analista")
    prefs = [f for f in cfg["analista"] if f in FERRAMENTAS_ANALISTA]
    aceitaveis = [f for f in prefs if sit[f] in ("cresce", "segue")]
    alvo = aceitaveis[0] if aceitaveis else None
    if atual and alvo and atual != alvo and (sit[atual] in ("sai", "para") or (alvo == prefs[0] and sit[alvo] == "cresce")):
        razao = motivo(atual) if sit[atual] in ("sai", "para") else f"{alvo} é a preferida e está ok"
        acoes.append(("parar", ["analista"], f"analista muda para {alvo}: {razao}"))
        acoes.append(("abrir", alvo, "analista", f"analista no {alvo}"))
    elif atual and not alvo and sit[atual] == "para":
        acoes.append(("parar", ["analista"], f"nenhuma ferramenta aguenta a analista: {motivo(atual)}"))
    elif not atual and alvo:
        acoes.append(("abrir", alvo, "analista", f"analista no {alvo}"))
    return acoes


# ---------- despertador


def _painel():
    import importlib.util
    spec = importlib.util.spec_from_file_location("painel_servidor", os.path.join(EQUIPE_HOME, "painel", "servidor.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def atividade(nomes):
    """nome → {"tipo", "h", "parado_s", "pergunta"} do último evento da sessão de cada agente vivo."""
    painel = _painel()
    mapa = painel.sessoes()
    out = {}
    for nome in nomes:
        if nome not in mapa:
            continue
        ferr, arq = mapa[nome]
        cons = (painel.console_claude if ferr == "claude" else painel.console_codex)(arq, 30)
        if not cons:
            continue
        # Mensagem que chega (inclusive o próprio DESPERTADOR) não é atividade do agente: conta o que ELE fez.
        dele = [e for e in cons if e["tipo"] != "entrada"] or cons
        ult = dele[-1]
        out[nome] = {"tipo": ult["tipo"], "h": ult["h"], "txt": ult.get("txt", ""),
                     "parado_s": painel.segundos_desde(ult["h"]), "pergunta": painel.pergunta_pendente(cons)}
    return out, painel


def fila(painel):
    conta = {}
    for i in painel.itens():
        conta[i["status"]] = conta.get(i["status"], 0) + 1
    return conta


def texto_despertar(nome, minutos, conta, perguntas):
    if nome == "analista":
        partes = [f"DESPERTADOR (supervisor): você terminou a vez e está parada há {minutos} min. Não espere aviso:"
                  " rode o ciclo agora (passo 0 e o primeiro passo de 1 a 7 com trabalho)."]
        partes.append("Fila: " + (", ".join(f"{v} {k}" for k, v in sorted(conta.items())) or "vazia") + ".")
        if conta.get("PROPOSTO", 0) < 6:
            partes.append("Menos de 6 PROPOSTO: faça uma rodada de descoberta (passos 5 e 6: varredura, pesquisa,"
                          " ideias, UX) e proponha itens com evidência; fila curta deixa implementador parado.")
        for n, p in perguntas:
            partes.append(f"{n} espera resposta sua: {p[:200]}")
        partes.append("Se estiver no Codex ou sem o monitor, este despertador é o seu pulso: não precisa recriar nada.")
        return " ".join(partes)
    return (f"DESPERTADOR (supervisor): você terminou a vez e está parado há {minutos} min. Releia o seu diário e"
            f" continue: AJUSTE e APROVADO seus primeiro; depois `equipe limites pode-pegar {nome}` e o próximo"
            " da `equipe itens fila`. Bloqueado? Escreva a pergunta à analista pelo `equipe msg` e siga com outra coisa.")


def planejar_despertar(ativ, vivos_agora, lim, cfg, memoria, conta, agora):
    """Ações: ("cutucar", nome, texto), ("reiniciar", nome, ferramenta), ("perguntar", texto para a analista)."""
    acoes = []
    cut = memoria.setdefault("cutucadas", {})
    perguntas_vistas = memoria.setdefault("perguntas", {})
    pendentes = []
    for nome, a in sorted(ativ.items()):
        ferr = vivos_agora.get(nome)
        if ferr and lim.get(ferr, {}).get("nivel") == "esgotado":
            continue  # sem limite, cutucar não adianta: quem age é a regra de limites
        c = cut.get(nome) or {}
        if c.get("marca") and c["marca"] != a["h"]:
            cut.pop(nome, None)  # trabalhou desde o último despertador
            c = {}
        if a["tipo"] not in ("fala", "fim", "entrada") or a["parado_s"] is None:
            continue  # no meio de um comando (teste, build): não é parado
        if nome != "analista" and a.get("pergunta"):
            pendentes.append((nome, a["pergunta"]))
            if perguntas_vistas.get(nome) != a["h"] and a["parado_s"] >= 15 * 60:
                perguntas_vistas[nome] = a["h"]
                acoes.append(("perguntar", f"{nome} espera resposta sua há {a['parado_s'] // 60} min: {a['pergunta'][:300]}"))
            continue
        limite_min = cfg["despertar_analista_min"] if nome == "analista" else cfg["despertar_implementador_min"]
        if a["parado_s"] < limite_min * 60 or agora - c.get("t", 0) < limite_min * 60:
            continue
        if c.get("n", 0) >= cfg["reiniciar_apos"]:
            acoes.append(("reiniciar", nome, ferr))
            cut.pop(nome, None)
            continue
        acoes.append(("cutucar", nome, texto_despertar(nome, a["parado_s"] // 60, conta, pendentes if nome == "analista" else [])))
        cut[nome] = {"t": agora, "n": c.get("n", 0) + 1, "marca": a["h"]}
    return acoes


def despertar(vv, lim, cfg, memoria, executar=True):
    ativ, painel = atividade(vv)
    acoes = planejar_despertar(ativ, vv, lim, cfg, memoria, fila(painel), time.time())
    feito = []
    for a in acoes:
        if a[0] == "cutucar":
            desc = f"despertador para {a[1]} ({cfg['despertar_analista_min' if a[1] == 'analista' else 'despertar_implementador_min']}+ min parado, {memoria['cutucadas'][a[1]]['n']}º seguido)"
            if executar:
                subprocess.run([os.path.join(AQUI, "msg.sh"), a[1], a[2]], cwd=RAIZ,
                               env=dict(os.environ, AGENTE="supervisor"), capture_output=True, timeout=90)
        elif a[0] == "perguntar":
            desc = f"pergunta pendente levada à analista: {a[1][:80]}"
            if executar:
                avisar_analista(a[1])
        else:
            desc = f"reiniciar {a[1]} no {a[2]} ({cfg['reiniciar_apos']} despertadores sem resposta)"
            if executar:
                parar([a[1]], f"{cfg['reiniciar_apos']} despertadores sem resposta: reiniciando a sessão")
                abrir(a[2], a[1])
        if executar:
            registrar(desc)
        feito.append(desc)
    return feito


# ---------- execução


def parar(nomes, motivo):
    env = dict(os.environ, PARAR_SO=" ".join(nomes), MOTIVO=f"supervisor: {motivo}", AGENTE="supervisor")
    env.setdefault("ESPERA", "300")
    r = subprocess.run([os.path.join(AQUI, "parar.sh")], cwd=RAIZ, env=env, capture_output=True, text=True)
    # O resumo do parar.sh: "✔ claude-1 MEL-152, critério 3 feito" ou "⚠ … não confirmou".
    saida = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
    resumo = [" ".join(l.split()) for l in saida.split("Resumo", 1)[-1].splitlines() if l.strip().startswith(("✔", "⚠"))]
    return r.returncode == 0, ["; ".join(resumo)]


def abrir(ferramenta, nome):
    env = dict(os.environ, AGENTE="supervisor", TERMINAL_AGENTES="tmux")
    if nome == "analista":
        env["ANALISTA_FERRAMENTA"] = ferramenta
        args = ["0", "0", "1", "1"]
    else:
        n = nome.split("-")[1]
        args = {"claude": ["1", "0", "0", n], "codex": ["0", "1", "0", n], "deep": ["0", "0", "0", n]}[ferramenta]
        if ferramenta == "deep":
            env["DEEP_N"] = "1"
    r = subprocess.run([os.path.join(AQUI, "abrir.sh"), *args], cwd=RAIZ, env=env, capture_output=True, text=True)
    linhas = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(("abertos:", "pulando"))]
    return r.returncode == 0, linhas[-1:] or [""]


def avisar_analista(txt):
    subprocess.run([os.path.join(AQUI, "msg.sh"), "analista", f"supervisor: {txt}"], cwd=RAIZ,
                   env=dict(os.environ, AGENTE="supervisor"), capture_output=True, timeout=90)


def volta(executar=True):
    cfg = config()
    if os.path.exists(PAUSA) and not os.environ.get("SUPERVISOR_IGNORAR_PAUSA"):
        return "equipe em PAUSA pelo dono: nada a fazer"
    # SUPERVISOR_LIMITES=arquivo.json: limites forçados (teste de ponta a ponta, testes/e2e-supervisor.sh)
    falsos = os.environ.get("SUPERVISOR_LIMITES")
    lim = ler_json(falsos, None) if falsos else limites.resumo(esperar=True)
    vv = vivos()
    memoria = ler_json(MEMORIA, {})
    acoes = planejar(lim, vv, cfg, memoria, time.time())
    ativo = executar and cfg.get("ativo", True)
    try:
        acordou = despertar(vv, lim, cfg, memoria if ativo else json.loads(json.dumps(memoria)), ativo)
    except Exception as e:  # noqa: BLE001 - despertador com problema não impede a regra de limites
        registrar(f"erro no despertador: {e}")
        acordou = []
    gravar_json(MEMORIA, memoria) if ativo else None
    if not acoes:
        resto = f"nada a fazer nos limites (claude {lim['claude']['nivel']}, codex {lim['codex']['nivel']}; vivos: {' '.join(sorted(vv)) or 'nenhum'})"
        return "\n".join(acordou + [resto]) if acordou else resto
    if not ativo:
        return "\n".join(("faria: " if executar else "") + d for d in [descrever(a) for a in acoes] + acordou)
    feito = []
    for a in acoes:
        if a[0] == "parar":
            ok, saida = parar(a[1], a[2])
            ferrs = {vv.get(n) for n in a[1] if n != "analista"} - {None}
            for f in ferrs:
                memoria.setdefault("parou", {})[f] = time.time()
        else:
            ok, saida = abrir(a[1], a[2])
        registrar(f"{descrever(a)} → {'ok' if ok else 'FALHOU'} {saida[0]}")
        feito.append(descrever(a))
    gravar_json(MEMORIA, memoria)
    avisar_analista("; ".join(feito))
    return "\n".join(feito + acordou)


def descrever(a):
    if a[0] == "parar":
        return f"parar {' '.join(a[1])} ({a[2]})"
    return f"abrir {a[2]} no {a[1]} ({a[3]})"


def rodando():
    try:
        pid = int(open(PID).read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def loop():
    if rodando():
        print(f"supervisor já está rodando (pid {rodando()})")
        return 0
    with open(PID, "w") as f:
        f.write(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    registrar("supervisor ligado")
    try:
        while True:
            try:
                r = volta()
                if not r.startswith(("nada a fazer nos limites", "equipe em PAUSA")):
                    print(r, flush=True)
            except Exception as e:  # noqa: BLE001 - uma volta ruim não derruba o supervisor
                registrar(f"erro na volta: {e}")
            time.sleep(max(60, int(config()["intervalo_s"])))
    finally:
        registrar("supervisor desligado")
        try:
            os.remove(PID)
        except OSError:
            pass


def main(args):
    cmd = args[0] if args else "ver"
    if cmd == "plano":
        print(volta(executar=False))
    elif cmd == "uma-vez":
        print(volta())
    elif cmd == "rodar":
        return loop()
    elif cmd == "inicial":
        # equipe subir: "<claudes> <codex> <deep> <ferramenta da analista>" que os limites permitem agora
        cfg = config()
        lim = limites.resumo(esperar=True)
        pedido = {"claude": int(args[1]), "codex": int(args[2]), "deep": int(args[3]) if len(args) > 3 else 0}
        sit = {f: situacao(lim[f], cfg["parar_em"]) if f in lim else "cresce" for f in FERRAMENTAS}
        n = {f: 0 if sit[f] == "para" else pedido[f] for f in FERRAMENTAS}
        prefs = [f for f in cfg["analista"] if f in FERRAMENTAS_ANALISTA and sit.get(f) in ("cresce", "segue")] or ["claude"]
        for f in FERRAMENTAS:
            if n[f] < pedido[f]:
                print(f"supervisor: {f} {lim[f]['nivel']}, não abro implementador {f} agora ({lim[f]['recomendacao']})", file=sys.stderr)
        print(n["claude"], n["codex"], n["deep"], prefs[0])
    elif cmd == "config":
        # equipe subir CLAUDE=2 CODEX=1 → os números pedidos viram o alvo do supervisor
        cfg = {**PADRAO, **ler_json(CONFIG, {})}
        for a in args[1:]:
            chave, _, valor = a.partition("=")
            if chave in FERRAMENTAS and valor.isdigit():
                cfg["implementadores"][chave] = int(valor)
            elif chave == "primeiro" and valor.isdigit():
                cfg["primeiro"] = int(valor)
            elif chave == "analista" and valor:
                cfg["analista"] = valor.split(",")
            elif chave == "ativo":
                cfg["ativo"] = valor not in ("0", "false", "nao", "não")
        gravar_json(CONFIG, cfg)
        print(json.dumps(cfg, ensure_ascii=False))
    elif cmd == "ver":
        pid = rodando()
        print(f"supervisor: {'rodando (pid %d)' % pid if pid else 'parado'}")
        print(json.dumps(config(), ensure_ascii=False))
        try:
            print("".join(open(LOG, encoding="utf-8").readlines()[-8:]).rstrip())
        except OSError:
            pass
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
