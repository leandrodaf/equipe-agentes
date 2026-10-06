#!/usr/bin/env python3
"""Limites de uso do Claude e do Codex: quanto já foi gasto de cada janela e se dá para pegar trabalho novo.

    equipe limites                       → resumo legível das três ferramentas
    equipe limites --json                → o mesmo em JSON (o painel usa resumo())
    equipe limites pode-pegar <NOME>     → sai 0 se dá para pegar item novo, 1 se não (diz o motivo)

Três ferramentas: claude (plano Max), codex (plano ChatGPT) e deep (DeepSeek pelo DEEP_COMANDO do config, padrão
`claude-deep`: o Claude Code apontado para a API da DeepSeek; cobra por uso, então o limite é o saldo da conta).

Todos os agentes de uma ferramenta dividem a mesma conta: o limite é da equipe, não do agente.

- Codex: cada sessão em ~/.codex/sessions grava `rate_limits` (janelas, % usado, reset, créditos)
  a cada resposta. Vale a leitura mais recente; se o reset dela já passou, a janela zerou.
- Claude: o endpoint de uso da conta (o mesmo do /usage do Claude Code), com o token OAuth de
  ~/.claude/.credentials.json. Só lê o token: quem renova é o próprio Claude Code. A resposta fica
  em .equipe/estado/limites-claude.json por 5 min; se a consulta falhar, usa a última guardada.
- DeepSeek: GET /user/balance com a chave de DEEPSEEK_API_KEY ou, sem ela, a da função DEEP_COMANDO
  do ~/.zshrc (lida na hora, nunca gravada). Saldo em .equipe/estado/limites-deep.json por 10 min.
  Faixas em dólar (LIMITE_DEEP="atencao,critico,esgotado", padrão 1.5,0.75,0.25).
"""

import glob
import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

CFG = config.carregar(exigir=False)
RAIZ = CFG["RAIZ"]
ESTADO = CFG["ESTADO"]
CACHE_CLAUDE = os.path.join(ESTADO, "limites-claude.json")
HOME = os.path.expanduser("~")
SESSOES_CODEX = os.path.join(HOME, ".codex", "sessions")
CREDENCIAIS_CLAUDE = os.path.join(HOME, ".claude", ".credentials.json")
URL_USO_CLAUDE = "https://api.anthropic.com/api/oauth/usage"
VALIDADE_CACHE = 300

# Ordem importa: a pior janela decide a situação da ferramenta.
NIVEIS = ["ok", "atencao", "critico", "esgotado"]
RECOMENDACAO = {
    "ok": "pode pegar item novo",
    "atencao": "prefira terminar o que tem; item novo só se for pequeno",
    "critico": "não pegue item novo: termine ou entregue o atual, faça commit WIP e anote o ponto de parada no diário",
    "esgotado": "sem limite: tudo o que usa esta ferramenta para até o reset",
}


def _agora():
    return time.time()


def nome_janela(minutos):
    if not minutos:
        return "janela"
    if minutos <= 360:
        return f"{round(minutos / 60)} horas"
    if minutos == 10080:
        return "semana"
    return f"{round(minutos / 1440)} dias"


def nivel(usado, inicio, reset, agora=None):
    """Situação de uma janela pelo % usado e pelo ritmo (onde termina se continuar no passo atual)."""
    agora = agora or _agora()
    if usado >= 98:
        return "esgotado"
    if usado >= 85:
        return "critico"
    if usado >= 70:
        return "atencao"
    if inicio and reset and reset > inicio:
        decorrido = (agora - inicio) / (reset - inicio)
        # Só julga o ritmo depois de 15% da janela, senão o começo dela distorce a conta.
        if decorrido >= 0.15 and usado >= 40 and usado / decorrido >= 110:
            return "atencao"
    return "ok"


def janela(nome, usado, reset, minutos=None, agora=None):
    agora = agora or _agora()
    if reset and reset <= agora:
        usado = 0.0  # a janela já virou desde a leitura
    inicio = reset - minutos * 60 if reset and minutos else None
    j = {
        "nome": nome,
        "usado": round(float(usado or 0), 1),
        "reset": reset,
        "reset_txt": hora_reset(reset, agora),
        "nivel": nivel(float(usado or 0), inicio, reset, agora),
    }
    if inicio and reset > inicio and reset > agora:
        decorrido = max((agora - inicio) / (reset - inicio), 0.01)
        j["ritmo"] = round(j["usado"] / decorrido)
        if j["ritmo"] > 100 and 0 < j["usado"] < 100:
            # No passo atual, quando chega a 100%: só interessa se for antes do reset.
            por_s = j["usado"] / (agora - inicio)
            j["esgota"] = agora + (100 - j["usado"]) / por_s
            j["esgota_txt"] = hora_reset(j["esgota"], agora)
    return j


def hora_reset(reset, agora=None):
    if not reset:
        return ""
    agora = agora or _agora()
    falta = reset - agora
    quando = datetime.fromtimestamp(reset)
    if falta <= 0:
        return "já zerou"
    if falta < 3600:
        return f"em {int(falta // 60)} min ({quando:%H:%M})"
    if falta < 86400 and quando.date() == datetime.fromtimestamp(agora).date():
        return f"às {quando:%H:%M}"
    return f"{quando:%d/%m %H:%M}"


def consolidar(ferramenta, janelas, extra=None, lido_em=None, erro=None):
    pior = max((j["nivel"] for j in janelas), key=NIVEIS.index, default="ok")
    res = {
        "ferramenta": ferramenta,
        "janelas": janelas,
        "nivel": pior,
        "recomendacao": RECOMENDACAO[pior],
        "lido_em": lido_em,
        "extra": extra,
        "erro": erro,
    }
    if pior in ("critico", "esgotado"):
        resets = [j["reset"] for j in janelas if j["nivel"] == pior and j.get("reset")]
        if resets:
            res["libera"] = hora_reset(max(resets))
            res["recomendacao"] += f" (libera {res['libera']})"
    if not janelas:
        res["nivel"] = "desconhecido"
        res["recomendacao"] = "sem leitura de limite; siga normalmente e confira de novo depois"
    return res


# ---------- Codex


def _ultima_leitura_codex(arquivos):
    for caminho in arquivos:
        try:
            with open(caminho, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 300_000))
                linhas = f.read().decode("utf-8", "replace").splitlines()
        except OSError:
            continue
        for l in reversed(linhas):
            if '"rate_limits"' not in l:
                continue
            try:
                d = json.loads(l)
            except ValueError:
                continue
            rl = (d.get("payload") or {}).get("rate_limits")
            if rl and (rl.get("primary") or rl.get("secondary")):
                return d.get("timestamp", ""), rl
    return None, None


def codex(agora=None):
    agora = agora or _agora()
    arquivos = sorted(glob.glob(os.path.join(SESSOES_CODEX, "*", "*", "*", "*.jsonl")), key=os.path.getmtime, reverse=True)[:15]
    quando, rl = _ultima_leitura_codex(arquivos)
    if not rl:
        return consolidar("codex", [], erro="nenhuma sessão do Codex com leitura de limite")
    janelas = []
    for chave in ("primary", "secondary"):
        p = rl.get(chave)
        if p:
            janelas.append(janela(nome_janela(p.get("window_minutes")), p.get("used_percent", 0), p.get("resets_at"), p.get("window_minutes"), agora))
    if rl.get("rate_limit_reached_type"):
        for j in janelas:
            if j["usado"] > 0:
                j["nivel"] = "esgotado"
    cred = rl.get("credits") or {}
    extra = {
        "plano": rl.get("plan_type"),
        "creditos": "ilimitado" if cred.get("unlimited") else (cred.get("balance") if cred.get("has_credits") else "sem créditos extras"),
    }
    return consolidar("codex", janelas, extra, lido_em=quando)


# ---------- Claude


def _consultar_claude():
    with open(CREDENCIAIS_CLAUDE, encoding="utf-8") as f:
        oauth = json.load(f)["claudeAiOauth"]
    if oauth.get("expiresAt") and oauth["expiresAt"] / 1000 < _agora():
        raise RuntimeError("token do Claude expirado (abra o Claude Code para ele renovar)")
    req = urllib.request.Request(URL_USO_CLAUDE, headers={
        "Authorization": "Bearer " + oauth["accessToken"],
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "equipe-agentes",
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        dados = json.load(r)
    dados["_plano"] = oauth.get("subscriptionType")
    return dados


def _ler_cache():
    try:
        with open(CACHE_CLAUDE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _gravar_cache(dados):
    os.makedirs(ESTADO, exist_ok=True)
    tmp = CACHE_CLAUDE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"t": _agora(), "dados": dados}, f)
    os.replace(tmp, CACHE_CLAUDE)


_atualizando = threading.Lock()


def _atualizar_claude():
    try:
        _gravar_cache(_consultar_claude())
        return None
    except Exception as e:  # noqa: BLE001 - sem rede ou token: usa a última leitura guardada
        return str(e)[:200]


def _ts(iso):
    try:
        return datetime.fromisoformat(iso).timestamp() if iso else None
    except ValueError:
        return None


def claude_de(dados, agora=None, lido_em=None, erro=None):
    agora = agora or _agora()
    janelas = []
    for chave, nome, minutos in (("five_hour", "5 horas", 300), ("seven_day", "semana", 10080),
                                 ("seven_day_opus", "semana (Opus)", 10080), ("seven_day_sonnet", "semana (Sonnet)", 10080)):
        p = dados.get(chave)
        if p and p.get("utilization") is not None:
            janelas.append(janela(nome, p["utilization"], _ts(p.get("resets_at")), minutos, agora))
    for l in dados.get("limits") or []:
        modelo = (((l.get("scope") or {}).get("model")) or {}).get("display_name")
        if l.get("kind") == "weekly_scoped" and modelo and l.get("percent"):
            janelas.append(janela(f"semana ({modelo})", l["percent"], _ts(l.get("resets_at")), 10080, agora))
    ext = dados.get("extra_usage") or {}
    extra = {
        "plano": dados.get("_plano"),
        "creditos": "uso extra ligado" if ext.get("is_enabled") else "sem créditos extras",
    }
    return consolidar("claude", janelas, extra, lido_em=lido_em, erro=erro)


def claude(agora=None, esperar=True):
    """esperar=False (painel): devolve o que está guardado e atualiza em segundo plano."""
    agora = agora or _agora()
    cache = _ler_cache()
    erro = None
    if not cache or agora - cache.get("t", 0) > VALIDADE_CACHE:
        if esperar:
            with _atualizando:
                erro = _atualizar_claude()
            cache = _ler_cache() or cache
        elif _atualizando.acquire(blocking=False):
            def fundo():
                try:
                    _atualizar_claude()
                finally:
                    _atualizando.release()
            threading.Thread(target=fundo, daemon=True).start()
    if not cache:
        return consolidar("claude", [], erro=erro or "ainda sem leitura")
    lido = datetime.fromtimestamp(cache["t"]).isoformat(timespec="seconds")
    return claude_de(cache["dados"], agora, lido_em=lido, erro=erro)


# ---------- DeepSeek


CACHE_DEEP = os.path.join(ESTADO, "limites-deep.json")
_atualizando_deep = threading.Lock()


def _chave_deep():
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    import re
    import subprocess
    cmd = CFG["DEEP_COMANDO"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", cmd):
        raise RuntimeError(f"DEEP_COMANDO inválido: {cmd}")
    f = subprocess.run(["zsh", "-ic", f"functions {cmd}"], capture_output=True, text=True, timeout=20).stdout
    m = re.search(r"ANTHROPIC_AUTH_TOKEN=(\S+)", f)
    if not m:
        raise RuntimeError(f"sem chave da DeepSeek (DEEPSEEK_API_KEY ou função {cmd} no ~/.zshrc)")
    return m.group(1).strip("'\"")


def _atualizar_deep():
    try:
        req = urllib.request.Request("https://api.deepseek.com/user/balance",
                                     headers={"Authorization": "Bearer " + _chave_deep(), "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            dados = json.load(r)
        os.makedirs(ESTADO, exist_ok=True)
        tmp = CACHE_DEEP + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"t": _agora(), "dados": dados}, f)
        os.replace(tmp, CACHE_DEEP)
        return None
    except Exception as e:  # noqa: BLE001 - sem rede ou chave: usa a última leitura guardada
        return str(e)[:200]


def faixas_deep():
    try:
        a, c, e = (float(x) for x in os.environ.get("LIMITE_DEEP", "1.5,0.75,0.25").split(","))
        return a, c, e
    except ValueError:
        return 1.5, 0.75, 0.25


def deep_de(dados, lido_em=None, erro=None):
    infos = dados.get("balance_infos") or []
    info = next((i for i in infos if i.get("currency") == "USD"), infos[0] if infos else None)
    if not info:
        return consolidar("deep", [], erro=erro or "sem saldo na resposta")
    saldo = float(info.get("total_balance") or 0)
    atencao, critico, esgotado = faixas_deep()
    if not dados.get("is_available", True) or saldo <= esgotado:
        nivel_ = "esgotado"
    elif saldo <= critico:
        nivel_ = "critico"
    elif saldo <= atencao:
        nivel_ = "atencao"
    else:
        nivel_ = "ok"
    moeda = "US$" if info.get("currency") == "USD" else info.get("currency", "")
    rec = RECOMENDACAO[nivel_]
    if nivel_ != "ok":
        rec += " (recarregue em platform.deepseek.com)"
    return {
        "ferramenta": "deep", "janelas": [], "nivel": nivel_, "recomendacao": rec, "lido_em": lido_em, "erro": erro,
        "saldo": saldo, "saldo_txt": f"{moeda} {saldo:.2f}".replace(".", ","),
        "extra": {"plano": "DeepSeek, por uso", "creditos": f"saldo {moeda} {saldo:.2f}".replace(".", ",")},
    }


def deep(agora=None, esperar=True):
    agora = agora or _agora()
    try:
        with open(CACHE_DEEP, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = None
    erro = None
    if not cache or agora - cache.get("t", 0) > 2 * VALIDADE_CACHE:
        if esperar:
            with _atualizando_deep:
                erro = _atualizar_deep()
        elif _atualizando_deep.acquire(blocking=False):
            def fundo():
                try:
                    _atualizar_deep()
                finally:
                    _atualizando_deep.release()
            threading.Thread(target=fundo, daemon=True).start()
        try:
            with open(CACHE_DEEP, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            pass
    if not cache:
        return consolidar("deep", [], erro=erro or "ainda sem leitura")
    return deep_de(cache["dados"], datetime.fromtimestamp(cache["t"]).isoformat(timespec="seconds"), erro)


# ---------- uso


def usa_deep():
    """A DeepSeek só é consultada se o projeto usa deep-N (N_DEEP no config) ou há chave no ambiente."""
    return CFG.get("N_DEEP", "0") not in ("", "0") or bool(os.environ.get("DEEPSEEK_API_KEY"))


def resumo(esperar=False):
    r = {"claude": claude(esperar=esperar), "codex": codex()}
    if usa_deep():
        r["deep"] = deep(esperar=esperar)
    return r


def ferramenta_do_agente(nome):
    for f in ("codex", "deep"):
        if nome == f or nome.startswith(f + "-"):
            return f
    return "claude"


def texto(res):
    rotulo = {"ok": "ok", "atencao": "ATENÇÃO", "critico": "CRÍTICO", "esgotado": "ESGOTADO", "desconhecido": "?"}
    out = []
    for f in ("claude", "codex", "deep"):
        r = res.get(f)
        if not r:
            continue
        plano = (r.get("extra") or {}).get("plano")
        out.append(f"{f}{f' ({plano})' if plano else ''}: {rotulo[r['nivel']]} — {r['recomendacao']}")
        for j in r["janelas"]:
            ritmo = f", no ritmo atual acaba {j['esgota_txt']}, antes de zerar" if j.get("esgota") else ""
            out.append(f"  {j['nome']}: {j['usado']:.0f}% usado, zera {j['reset_txt']}{ritmo}")
        if r.get("extra"):
            out.append(f"  créditos: {r['extra']['creditos']}")
        if r.get("erro"):
            out.append(f"  aviso: {r['erro']}")
    return "\n".join(out)


def main(args):
    if args[:1] == ["pode-pegar"]:
        if len(args) < 2:
            print("uso: equipe limites pode-pegar <SEU NOME>", file=sys.stderr)
            return 2
        f = ferramenta_do_agente(args[1])
        r = {"claude": claude, "codex": lambda **_: codex(), "deep": deep}[f](esperar=True)
        if r["nivel"] in ("critico", "esgotado"):
            print(f"NÃO: {f} {r['nivel']} — {r['recomendacao']}")
            return 1
        print(f"SIM: {f} {r['nivel']} — {r['recomendacao']}")
        return 0
    res = resumo(esperar=True)
    print(json.dumps(res, ensure_ascii=False, indent=1) if "--json" in args else texto(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
