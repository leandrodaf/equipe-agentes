"""Os testes rodam contra um projeto descartável (EQUIPE_RAIZ) com PROJETO=teste, antes de qualquer
módulo do motor ser importado: nada aqui lê nem mexe no projeto de verdade."""
import atexit
import os
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.dirname(AQUI)
sys.path[:0] = [os.path.join(HOME, "lib"), os.path.join(HOME, "painel")]

RAIZ = tempfile.mkdtemp(prefix="equipe-teste-")
atexit.register(shutil.rmtree, RAIZ, True)
os.makedirs(os.path.join(RAIZ, ".equipe", "estado"))
with open(os.path.join(RAIZ, ".equipe", "config.env"), "w", encoding="utf-8") as f:
    f.write("PROJETO=teste\nPREFIXO=MEL\n")
os.environ["EQUIPE_RAIZ"] = RAIZ
