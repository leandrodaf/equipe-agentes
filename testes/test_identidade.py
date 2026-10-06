import json
import tempfile
import unittest
from pathlib import Path

from testes import RAIZ  # noqa: F401  (o projeto descartável vem antes do motor)
import identidade  # noqa: E402


class NomeDoPromptTest(unittest.TestCase):
    def test_prompts_de_agente(self):
        self.assertEqual(identidade.nome_do_prompt("# Equipe teste · papel: analista\nSEU NOME: analista\n…"), "analista")
        self.assertEqual(identidade.nome_do_prompt("# Equipe teste · papel: implementador\nSEU NOME: claude-2\n…"), "claude-2")
        self.assertEqual(identidade.nome_do_prompt("# Equipe teste · papel: implementador\n\nSEU NOME: codex-1  (nota"), "codex-1")
        self.assertEqual(identidade.nome_do_prompt("# Equipe teste · papel: teste-pausa\nSEU NOME: deep-90\nTESTE"), "deep-90")

    def test_agente_de_outro_projeto_nao_e_deste(self):
        self.assertIsNone(identidade.nome_do_prompt("# Equipe outro · papel: implementador\nSEU NOME: claude-2\n…"))
        self.assertEqual(identidade.nome_do_prompt("# Equipe outro · papel: analista\n…", "outro"), "analista")

    def test_processo_pelo_nome_com_projeto(self):
        from unittest.mock import patch
        with patch.object(identidade, "argumentos", return_value=["claude", "-n", "claude-3@teste", "oi"]):
            self.assertEqual(identidade.nome_do_processo(1), "claude-3")
        with patch.object(identidade, "argumentos", return_value=["claude", "-n", "claude-3@outro", "oi"]):
            self.assertIsNone(identidade.nome_do_processo(1))
        with patch.object(identidade, "argumentos", return_value=["claude", "-n", "claude-3", "oi"]):
            self.assertIsNone(identidade.nome_do_processo(1))
        with patch.object(identidade, "argumentos", return_value=["tmux", "new-window", "-n", "claude-3@teste"]):
            self.assertIsNone(identidade.nome_do_processo(1))

    def test_sessao_aberta_para_outra_coisa_nao_e_agente(self):
        for texto in (
            "analisa /home/x/prompts/analista.md e refina",
            "olha isto:\n# Equipe teste · papel: analista",
            "# Equipe teste · papel: implementador\n\nSEU NOME: ______",
            "# Papel: implementador\n\nSEU NOME: claude-1",
            "corrija o painel; ex.: SEU NOME: claude-1",
            "",
        ):
            self.assertIsNone(identidade.nome_do_prompt(texto), texto)


class SessaoTest(unittest.TestCase):
    def jsonl(self, linhas):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        f.write("\n".join(json.dumps(l) for l in linhas))
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return f.name

    def test_so_o_primeiro_prompt_conta(self):
        claude = self.jsonl([
            {"type": "user", "isMeta": True, "message": {"content": "<local-command-caveat>…"}},
            {"type": "user", "message": {"content": "refina o prompt do analista"}},
            {"type": "user", "message": {"content": "# Equipe teste · papel: analista (colado depois)"}},
        ])
        self.assertIsNone(identidade.nome_da_sessao(claude))

    def test_codex_pula_o_contexto_injetado(self):
        codex = self.jsonl([
            {"type": "session_meta", "payload": {}},
            {"type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "# AGENTS.md instructions\n…"}]}},
            {"type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "<environment_context>…"}]}},
            {"type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "# Equipe teste · papel: implementador\nSEU NOME: codex-3\n"}]}},
        ])
        self.assertEqual(identidade.nome_da_sessao(codex), "codex-3")


if __name__ == "__main__":
    unittest.main()
