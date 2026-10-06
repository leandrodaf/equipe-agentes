# Carregado (source) por todos os scripts shell da equipe: acha o projeto e exporta a configuração
# (RAIZ, ESTADO, PROJETO, SESSAO_TMUX, FILA, PREFIXO, GATE… — a lista está em lib/config.py).
# EQUIPE_HOME é a pasta deste repositório (o motor); RAIZ é o projeto onde a equipe trabalha.
EQUIPE_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_cfg="$(python3 "$EQUIPE_HOME/lib/config.py" shell)" || exit 2
eval "$_cfg"
unset _cfg
export EQUIPE_RAIZ="$RAIZ" EQUIPE_HOME
LIB="$EQUIPE_HOME/lib"
mkdir -p "$ESTADO"

# Nome de agente válido: analista, claude-N, codex-N, deep-N.
NOME_AGENTE_RE='^(analista|(claude|codex|deep)-[0-9]+)$'
