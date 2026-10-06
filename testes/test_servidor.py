"""Regressões do histórico e da identificação das sessões do painel."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from testes import HOME  # noqa: E402  (o projeto descartável vem antes do motor)

spec = importlib.util.spec_from_file_location("painel", Path(HOME, "painel", "servidor.py"))
painel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(painel)


class HistoricoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)

    def sessao(self, linhas):
        arquivo = self.raiz / "sessao.jsonl"
        arquivo.write_text("\n".join(json.dumps(l) for l in linhas))
        return str(arquivo)

    def test_nome_na_saida_de_ferramenta_nao_identifica_analista(self):
        arquivo = self.sessao([
            {"type": "response_item", "payload": {"type": "function_call_output", "output": "# Equipe teste · papel: analista"}},
            {"type": "response_item", "payload": {"role": "user", "content": [{"text": "Melhore o painel"}]}},
        ])
        self.assertIsNone(painel.primeiro_nome(arquivo))

    def test_nome_no_prompt_do_usuario(self):
        for texto, esperado in [("# Equipe teste · papel: analista\nCoordene a equipe", "analista"), ("# Equipe teste · papel: implementador\nSEU NOME: codex-2\nImplemente", "codex-2")]:
            arquivo = self.sessao([{"type": "user", "message": {"content": texto}}])
            self.assertEqual(painel.primeiro_nome(arquivo), esperado)

    def test_fala_completa_sem_prompt_ou_ferramentas(self):
        texto = "Primeiro parágrafo.\n\n" + "Resposta importante. " * 100
        arquivo = self.sessao([
            {"type": "response_item", "timestamp": "2026-10-04T14:00:00Z", "payload": {"type": "message", "role": "user", "content": [{"text": "Prompt interno"}]}},
            {"type": "response_item", "timestamp": "2026-10-04T14:01:00Z", "payload": {"type": "message", "role": "assistant", "content": [{"text": texto}]}},
        ])
        with patch.object(painel, "ESTADO", str(self.raiz)):
            eventos = painel.conversa_analista({"analista": ("codex", arquivo)})
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["txt"], texto)
        self.assertEqual(eventos[0]["de"], "analista")

    def test_fala_claude_completa(self):
        texto = "Uma resposta.\n\n" + "Detalhes. " * 100
        arquivo = self.sessao([{"type": "assistant", "timestamp": "2026-10-04T14:00:00Z", "message": {"content": [{"type": "text", "text": texto}]}}])
        self.assertEqual(painel.console_claude(arquivo, 10, completo=True)[0]["txt"], texto)

    def test_log_multilinha_destino_e_ids_estaveis(self):
        (self.raiz / "mensagens.log").write_text("2026-10-04 12:00 · dono → analista (caixa) · Ideia\nsegunda linha\n2026-10-04 12:01 · dono → codex-1 (terminal) · Outra\n")
        with patch.object(painel, "ESTADO", str(self.raiz)):
            a = painel.conversa_analista({})
            b = painel.conversa_analista({})
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["txt"], "Ideia\nsegunda linha")
        self.assertEqual(a[0]["via"], "caixa")
        self.assertEqual(a[0]["id"], b[0]["id"])

    def test_artefatos_bloqueia_traversal_e_symlink(self):
        estado = self.raiz / ".equipe" / "estado"
        estado.mkdir(parents=True)
        (estado / "relatorio.md").write_text("# Resultado")
        segredo = self.raiz / "segredo.md"
        segredo.write_text("fora do acervo")
        (estado / "atalho.md").symlink_to(segredo)
        with patch.object(painel, "RAIZ", str(self.raiz)), patch.object(painel, "ESTADO", str(estado)):
            self.assertIsNotNone(painel.caminho_artefato(".equipe/estado/relatorio.md"))
            self.assertIsNone(painel.caminho_artefato(".equipe/estado/../../segredo.md"))
            self.assertIsNone(painel.caminho_artefato(".equipe/estado/atalho.md"))
            self.assertIsNone(painel.caminho_artefato(str(segredo)))

    def test_artefatos_vinculados_por_item(self):
        estado = self.raiz / ".equipe" / "estado"
        pasta = estado / "prints" / "MEL-121"
        pasta.mkdir(parents=True)
        (pasta / "mobile.png").write_bytes(b"imagem")
        with patch.object(painel, "RAIZ", str(self.raiz)), patch.object(painel, "ESTADO", str(estado)), patch.object(painel, "_cache_artefatos", {"t": 0, "arquivos": []}):
            arquivos = painel.artefatos()
        self.assertEqual(len(arquivos), 1)
        self.assertEqual(arquivos[0]["itens"], ["MEL-121"])
        self.assertEqual(arquivos[0]["tipo"], "imagem")


if __name__ == "__main__":
    unittest.main()
