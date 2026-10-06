"""Configuração, montagem do prompt e leitura da fila, num projeto descartável."""
import io
import os
import unittest
from contextlib import redirect_stdout

from testes import HOME, RAIZ
import config  # noqa: E402
import itens  # noqa: E402
import prompt  # noqa: E402


class ConfigTest(unittest.TestCase):
    def test_le_aspas_comentarios_e_padroes(self):
        caminho = os.path.join(RAIZ, "outro.env")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write('GATE="make check -j4"  # comentário\nexport PREFIXO=ab-c\n# DESCRICAO=ignorada\nlixo\n')
        self.addCleanup(os.remove, caminho)
        self.assertEqual(config.ler_env(caminho), {"GATE": "make check -j4", "PREFIXO": "ab-c"})

    def test_valores_derivados(self):
        c = config.carregar()
        self.assertEqual(c["PROJETO"], "teste")
        self.assertEqual(c["SESSAO_TMUX"], "equipe-teste")
        self.assertEqual(c["ESTADO"], os.path.join(RAIZ, ".equipe", "estado"))
        self.assertEqual(c["PREFIXO_MIN"], "mel")
        self.assertEqual(c["RAMO"], "main")
        self.assertTrue(c["SESSOES_CLAUDE"].endswith(RAIZ.replace("/", "-").replace("_", "-")))


class PromptTest(unittest.TestCase):
    def test_os_dois_papeis_montam_sem_valor_faltando(self):
        for papel, nome in (("analista", "analista"), ("implementador", "codex-2")):
            texto = prompt.montar(papel, nome)
            self.assertTrue(texto.startswith(f"# Equipe teste · papel: {papel}\nSEU NOME: {nome}\n"))
            self.assertNotIn("{{", texto)
            self.assertIn(RAIZ, texto)

    def test_contexto_do_projeto_sem_comentarios(self):
        caminho = os.path.join(RAIZ, ".equipe", "projeto.md")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("<!-- instrução do modelo -->\n## O que é\n\nUm app em {{RAMO}}.\n")
        self.addCleanup(os.remove, caminho)
        texto = prompt.montar("implementador", "claude-1")
        self.assertIn("# O projeto", texto)
        self.assertIn("Um app em main.", texto)
        self.assertNotIn("instrução do modelo", texto)

    def test_valor_desconhecido_para(self):
        with self.assertRaises(SystemExit):
            prompt.preencher("oi {{NAO_EXISTE}}", prompt.valores(config.carregar(), "x"), "teste")

    def test_roteiros_preenchem(self):
        v = prompt.valores(config.carregar(), "analista")
        for nome in ("faxina", "varredura", "pesquisa"):
            with open(os.path.join(HOME, "roteiros", f"{nome}.md"), encoding="utf-8") as f:
                self.assertNotIn("{{", prompt.preencher(f.read(), v, nome))


class FilaTest(unittest.TestCase):
    def test_fila_na_ordem_do_dono_e_depois_prioridade(self):
        with open(os.path.join(RAIZ, "MELHORIAS.md"), "w", encoding="utf-8") as f:
            f.write("""## MEL-001 · A
- Status: PROPOSTO
- Prioridade: P2

## MEL-002 · B
- Status: PROPOSTO
- Prioridade: P0

## MEL-003 · C
- Status: EM ANDAMENTO
- Responsável: claude-1

## MEL-004 · D
- Status: PROPOSTO
- Prioridade: P3
""")
        with open(os.path.join(RAIZ, ".equipe", "estado", "ordem.json"), "w", encoding="utf-8") as f:
            f.write('{"ids": ["MEL-004"]}')
        saida = io.StringIO()
        with redirect_stdout(saida):
            itens.main(["fila"])
        self.assertEqual([l.split(" | ")[0] for l in saida.getvalue().splitlines()], ["1. MEL-004", "2. MEL-002", "3. MEL-001"])
        saida = io.StringIO()
        with redirect_stdout(saida):
            itens.main(["EM"])
        self.assertEqual(saida.getvalue(), "MEL-003 | EM ANDAMENTO | claude-1 | -\n")


if __name__ == "__main__":
    unittest.main()
