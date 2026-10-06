"""Leitura dos limites do Claude e do Codex e a decisão de pegar item novo."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from testes import RAIZ  # noqa: F401,E402  (o projeto descartável vem antes do motor)
import limites  # noqa: E402

AGORA = 1_791_000_000.0
SEMANA = 10080


class NivelTest(unittest.TestCase):
    def test_faixas_pelo_percentual(self):
        for usado, esperado in [(10, "ok"), (70, "atencao"), (85, "critico"), (98, "esgotado")]:
            self.assertEqual(limites.nivel(usado, None, None, AGORA), esperado)

    def test_ritmo_acima_do_tempo_vira_atencao(self):
        # 60% gastos com só 30% da semana passada: acaba antes do reset.
        inicio = AGORA - 0.3 * SEMANA * 60
        self.assertEqual(limites.nivel(60, inicio, inicio + SEMANA * 60, AGORA), "atencao")

    def test_comeco_da_janela_nao_julga_ritmo(self):
        inicio = AGORA - 0.05 * SEMANA * 60
        self.assertEqual(limites.nivel(45, inicio, inicio + SEMANA * 60, AGORA), "ok")

    def test_janela_com_reset_passado_zera(self):
        j = limites.janela("semana", 99, AGORA - 10, SEMANA, AGORA)
        self.assertEqual((j["usado"], j["nivel"]), (0, "ok"))

    def test_estima_quando_acaba_antes_do_reset(self):
        reset = AGORA + 0.5 * SEMANA * 60  # metade da semana passou
        j = limites.janela("semana", 60, reset, SEMANA, AGORA)
        self.assertEqual(j["ritmo"], 120)
        self.assertLess(j["esgota"], reset)


class LeituraTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_codex_usa_a_leitura_mais_recente(self):
        pasta = os.path.join(self.temp.name, "2026", "10", "05")
        os.makedirs(pasta)
        rl = lambda p: {"primary": {"used_percent": p, "window_minutes": SEMANA, "resets_at": AGORA + 3600},
                        "credits": {"has_credits": False}, "plan_type": "prolite"}
        linhas = [
            {"timestamp": "t1", "type": "event_msg", "payload": {"type": "token_count", "rate_limits": rl(50)}},
            {"timestamp": "t2", "type": "event_msg", "payload": {"type": "token_count", "rate_limits": rl(91)}},
            {"timestamp": "t3", "type": "event_msg", "payload": {"type": "token_count", "rate_limits": {"primary": None}}},
        ]
        with open(os.path.join(pasta, "rollout.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(l) for l in linhas))
        with patch.object(limites, "SESSOES_CODEX", self.temp.name):
            r = limites.codex(AGORA)
        self.assertEqual((r["nivel"], r["lido_em"], r["janelas"][0]["usado"]), ("critico", "t2", 91))
        self.assertEqual(r["extra"]["plano"], "prolite")

    def test_codex_sem_sessao_fica_desconhecido(self):
        with patch.object(limites, "SESSOES_CODEX", self.temp.name):
            self.assertEqual(limites.codex(AGORA)["nivel"], "desconhecido")

    def test_claude_pior_janela_decide(self):
        dados = {
            "five_hour": {"utilization": 20, "resets_at": "2026-10-05T20:00:00+00:00"},
            "seven_day": {"utilization": 92, "resets_at": "2026-10-05T22:00:00+00:00"},
            "limits": [{"kind": "weekly_scoped", "percent": 0, "scope": {"model": {"display_name": "Fable"}}}],
            "extra_usage": {"is_enabled": False},
        }
        r = limites.claude_de(dados, AGORA)
        self.assertEqual(r["nivel"], "critico")
        self.assertEqual([j["nome"] for j in r["janelas"]], ["5 horas", "semana"])
        self.assertIn("libera", r["recomendacao"])

    def test_claude_falha_usa_cache_guardado(self):
        cache = os.path.join(self.temp.name, "limites-claude.json")
        with open(cache, "w") as f:
            json.dump({"t": AGORA - 3600, "dados": {"seven_day": {"utilization": 40, "resets_at": None}}}, f)
        with patch.object(limites, "CACHE_CLAUDE", cache), patch.object(limites, "_consultar_claude", side_effect=OSError("sem rede")):
            r = limites.claude(AGORA, esperar=True)
        self.assertEqual((r["nivel"], r["janelas"][0]["usado"]), ("ok", 40))
        self.assertIn("sem rede", r["erro"])


class DeepTest(unittest.TestCase):
    def test_faixas_do_saldo(self):
        for saldo, esperado in [("2.85", "ok"), ("1.20", "atencao"), ("0.50", "critico"), ("0.10", "esgotado")]:
            r = limites.deep_de({"is_available": True, "balance_infos": [{"currency": "USD", "total_balance": saldo}]})
            self.assertEqual(r["nivel"], esperado, saldo)
        self.assertEqual(r["saldo_txt"], "US$ 0,10")

    def test_conta_indisponivel_esgota(self):
        r = limites.deep_de({"is_available": False, "balance_infos": [{"currency": "USD", "total_balance": "9"}]})
        self.assertEqual(r["nivel"], "esgotado")

    def test_nome_do_agente(self):
        self.assertEqual([limites.ferramenta_do_agente(n) for n in ("deep-2", "codex-1", "claude-3", "analista")],
                         ["deep", "codex", "claude", "claude"])


class PodePegarTest(unittest.TestCase):
    def test_codigo_de_saida(self):
        critico = limites.consolidar("codex", [{"nome": "semana", "usado": 90, "reset": None, "reset_txt": "", "nivel": "critico"}])
        ok = limites.consolidar("claude", [{"nome": "semana", "usado": 10, "reset": None, "reset_txt": "", "nivel": "ok"}])
        with patch.object(limites, "codex", return_value=critico), patch.object(limites, "claude", return_value=ok), \
                patch("sys.stdout"):
            self.assertEqual(limites.main(["pode-pegar", "codex-2"]), 1)
            self.assertEqual(limites.main(["pode-pegar", "analista"]), 0)
            self.assertEqual(limites.main(["pode-pegar"]), 2)


if __name__ == "__main__":
    unittest.main()
