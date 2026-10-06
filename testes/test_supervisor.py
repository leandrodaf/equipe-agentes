"""Decisões do supervisor: quem para, quem abre e onde fica a analista."""
import os
import sys
import unittest

from testes import RAIZ  # noqa: F401,E402  (o projeto descartável vem antes do motor)
import supervisor  # noqa: E402

AGORA = 1_791_000_000.0
CFG = {**supervisor.PADRAO, "implementadores": {"claude": 2, "codex": 2}}


def lim(nivel, usado, libera=None):
    return {"nivel": nivel, "janelas": [{"usado": usado}], "libera": libera}


def plano(claude, codex, vivos, memoria=None, cfg=CFG):
    return supervisor.planejar({"claude": claude, "codex": codex}, vivos, cfg, memoria or {}, AGORA)


TODOS = {"analista": "claude", "claude-1": "claude", "claude-2": "claude", "codex-1": "codex", "codex-2": "codex"}


class PlanoTest(unittest.TestCase):
    def test_tudo_ok_e_completo_nao_faz_nada(self):
        self.assertEqual(plano(lim("ok", 10), lim("ok", 10), TODOS), [])

    def test_abre_quem_falta(self):
        vivos = {k: v for k, v in TODOS.items() if k != "codex-2"}
        self.assertEqual(plano(lim("ok", 10), lim("ok", 10), vivos), [("abrir", "codex", "codex-2", "codex ok")])

    def test_critico_so_muda_a_analista(self):
        acoes = plano(lim("critico", 90, "às 18:59"), lim("ok", 30), TODOS)
        self.assertEqual([a[0] for a in acoes], ["parar", "abrir"])
        self.assertEqual(acoes[0][1], ["analista"])
        self.assertEqual(acoes[1][:3], ("abrir", "codex", "analista"))

    def test_no_limite_para_os_implementadores_da_ferramenta(self):
        acoes = plano(lim("critico", 96), lim("ok", 30), TODOS)
        self.assertEqual(acoes[0], ("parar", ["claude-1", "claude-2"], "claude critico (96%)"))
        self.assertIn(("abrir", "codex", "analista", "analista no codex"), acoes)

    def test_nao_reabre_logo_depois_de_parar(self):
        vivos = {"analista": "codex", "codex-1": "codex", "codex-2": "codex"}
        recente = {"parou": {"claude": AGORA - 60}}
        self.assertEqual([a for a in plano(lim("ok", 0), lim("ok", 30), vivos, recente) if a[0] == "abrir" and a[1] == "claude" and a[2] != "analista"], [])
        antigo = {"parou": {"claude": AGORA - 3600}}
        abertos = [a[2] for a in plano(lim("ok", 0), lim("ok", 30), vivos, antigo) if a[0] == "abrir"]
        self.assertEqual(abertos, ["claude-1", "claude-2", "analista"])

    def test_analista_volta_para_a_preferida(self):
        vivos = dict(TODOS, analista="codex")
        acoes = plano(lim("ok", 5), lim("ok", 30), vivos)
        self.assertEqual(acoes, [("parar", ["analista"], "analista muda para claude: claude é a preferida e está ok"),
                                 ("abrir", "claude", "analista", "analista no claude")])

    def test_analista_em_atencao_na_reserva_nao_volta(self):
        vivos = dict(TODOS, analista="codex")
        self.assertEqual(plano(lim("atencao", 75), lim("ok", 30), vivos), [])

    def test_atencao_nao_abre_mas_nao_para(self):
        vivos = {"analista": "claude", "claude-1": "claude", "codex-1": "codex", "codex-2": "codex"}
        self.assertEqual(plano(lim("atencao", 75), lim("ok", 30), vivos), [])

    def test_as_duas_esgotadas_param_tudo(self):
        acoes = plano(lim("esgotado", 100), lim("esgotado", 100), TODOS)
        parados = sorted(n for a in acoes if a[0] == "parar" for n in a[1])
        self.assertEqual(parados, sorted(TODOS))
        self.assertFalse([a for a in acoes if a[0] == "abrir"])

    def test_deep_abre_e_para_pelo_saldo_e_nunca_recebe_a_analista(self):
        cfg = {**CFG, "implementadores": {"claude": 0, "codex": 0, "deep": 1}, "analista": ["deep", "codex"]}
        lims = {"claude": lim("esgotado", 100), "codex": lim("ok", 10), "deep": {"nivel": "ok", "janelas": []}}
        acoes = supervisor.planejar(lims, {}, cfg, {}, AGORA)
        self.assertEqual(acoes, [("abrir", "deep", "deep-1", "deep ok"), ("abrir", "codex", "analista", "analista no codex")])
        lims["deep"] = {"nivel": "esgotado", "janelas": [], "saldo_txt": "US$ 0,10"}
        acoes = supervisor.planejar(lims, {"deep-1": "deep", "analista": "codex"}, cfg, {}, AGORA)
        self.assertEqual(acoes, [("parar", ["deep-1"], "deep esgotado (US$ 0,10)")])

    def test_sem_leitura_conta_como_ok(self):
        self.assertEqual(plano({"nivel": "desconhecido", "janelas": []}, lim("ok", 1), TODOS), [])


def ativ(tipo="fala", parado_min=30, h="t1", pergunta=None):
    return {"tipo": tipo, "h": h, "txt": "", "parado_s": parado_min * 60, "pergunta": pergunta}


class DespertadorTest(unittest.TestCase):
    def acordar(self, atividades, memoria, vivos=None, lims=None, conta=None, agora=AGORA):
        vivos = vivos or {n: "claude" for n in atividades}
        lims = lims or {"claude": lim("ok", 10), "codex": lim("ok", 10)}
        return supervisor.planejar_despertar(atividades, vivos, lims, CFG, memoria, conta or {"PROPOSTO": 2}, agora)

    def test_analista_parada_recebe_despertador_com_descoberta(self):
        acoes = self.acordar({"analista": ativ(parado_min=20)}, {})
        self.assertEqual(acoes[0][:2], ("cutucar", "analista"))
        self.assertIn("rodada de descoberta", acoes[0][2])

    def test_nao_cutuca_antes_do_tempo_nem_no_meio_de_comando(self):
        self.assertEqual(self.acordar({"analista": ativ(parado_min=10)}, {}), [])
        self.assertEqual(self.acordar({"claude-1": ativ(tipo="acao", parado_min=90)}, {}), [])
        self.assertEqual(self.acordar({"claude-1": ativ(parado_min=20)}, {}), [])  # implementador: 25 min

    def test_nao_cutuca_em_ferramenta_esgotada(self):
        lims = {"claude": lim("esgotado", 100), "codex": lim("ok", 1)}
        self.assertEqual(self.acordar({"analista": ativ(parado_min=60)}, {}, lims=lims), [])

    def test_sem_resposta_reinicia_e_com_resposta_zera(self):
        memoria = {}
        for i in range(3):
            acoes = self.acordar({"codex-1": ativ(parado_min=60)}, memoria, vivos={"codex-1": "codex"}, agora=AGORA + i * 3600)
            self.assertEqual(acoes[0][0], "cutucar")
        acoes = self.acordar({"codex-1": ativ(parado_min=60)}, memoria, vivos={"codex-1": "codex"}, agora=AGORA + 4 * 3600)
        self.assertEqual(acoes, [("reiniciar", "codex-1", "codex")])
        # trabalhou depois do despertador (evento novo): a contagem recomeça
        memoria = {"cutucadas": {"codex-1": {"t": AGORA - 3600, "n": 2, "marca": "t1"}}}
        self.acordar({"codex-1": ativ(parado_min=60, h="t2")}, memoria, vivos={"codex-1": "codex"})
        self.assertEqual(memoria["cutucadas"]["codex-1"]["n"], 1)

    def test_pergunta_do_implementador_vai_para_a_analista(self):
        memoria = {}
        acoes = self.acordar({"claude-2": ativ(parado_min=20, pergunta="Uso a tabela nova?")}, memoria)
        self.assertEqual(acoes, [("perguntar", "claude-2 espera resposta sua há 20 min: Uso a tabela nova?")])
        self.assertEqual(self.acordar({"claude-2": ativ(parado_min=40, pergunta="Uso a tabela nova?")}, memoria), [])


if __name__ == "__main__":
    unittest.main()
