# equipe-agentes

Uma **equipe de agentes de código** trabalhando sozinha num repositório git: uma **analista** que
descobre, escreve, prioriza e revisa itens, e vários **implementadores** (Claude Code, Codex e,
opcionalmente, Claude Code apontado para a DeepSeek) que pegam itens da fila, implementam cada um
numa worktree própria, provam os critérios de aceitação, e integram no ramo principal depois do
aprovado. Um **supervisor** mantém a equipe dentro dos limites de uso de cada ferramenta e acorda
quem ficou parado, e um **painel web** mostra tudo ao vivo: a fila, o console de cada agente, as
mensagens, e deixa o dono pausar, reordenar e falar com a equipe.

Nasceu num projeto pessoal e foi desacoplado para servir a qualquer repositório: tudo o que é do
projeto fica numa pasta `.equipe/` dentro dele; o motor fica aqui.

> ⚠️ **Os agentes rodam sem pedir permissão** (`claude --dangerously-skip-permissions`,
> `codex --dangerously-bypass-approvals-and-sandbox`). Eles executam comandos e editam arquivos na
> sua máquina. Use numa máquina e num usuário em que você aceite isso, num repositório com backup
> remoto, e leia os prompts (`prompts/`) antes. As regras dos prompts proíbem `push --force`,
> `git stash`, `reset --hard` na árvore principal e tocar no ambiente do dono, mas regra de prompt
> não é sandbox.

## Como funciona

```
 dono ──► painel web (fila, consoles, mensagens, pausa)        supervisor (limites, despertador)
              │                                                        │
              ▼                                                        ▼
        ┌──────────── tmux "equipe-<projeto>": uma janela por agente ────────────┐
        │  analista            claude-1   claude-2   codex-1   deep-1   …         │
        │  escreve/revisa      implementam, cada um na sua worktree               │
        └───────────────────────────────┬────────────────────────────────────────┘
                                        ▼
            MELHORIAS.md (a fila, com o Protocolo)  ·  travas  ·  diários  ·  caixa de mensagens
                                        ▼
                     ramo principal (só fast-forward, com a trava de integração)
```

- **A fila** é um arquivo Markdown (padrão `MELHORIAS.md`) com itens `## MEL-NNN · Título`, cada um
  com Status, Prioridade, critérios de aceitação e um **Registro** onde todo agente só acrescenta
  linhas. Os estados: `PROPOSTO → EM ANDAMENTO → PRONTO PARA REVISÃO → APROVADO → INTEGRADO`.
- **Travas** (`equipe trava`) por `mkdir` atômico: `fila` para escrever na fila, `integracao` para
  mudar o ramo principal. Trava de agente morto ou de antes do boot se solta sozinha.
- **Identidade**: um processo só é o agente `claude-2` do projeto P se foi aberto com o prompt
  `# Equipe P · papel: …` / `SEU NOME: claude-2` (ou `-n claude-2@P`). Assim um Claude aberto à
  mão nunca é confundido com um agente, e **vários projetos podem ter equipes ao mesmo tempo**.
- **Mensagens** (`equipe msg`): para o Codex, pela fila da sessão (`codex queue`); para o Claude,
  digitado no terminal dele pelo tmux; sem sessão viva, numa caixa de entrada em arquivo.
- **Pausa e parada segura**: `equipe parar` avisa cada agente, mostra ao vivo cada passo da
  parada (commit WIP, travas soltas, servidores derrubados, diário) e só então fecha as sessões.
  Cada agente continua do próprio diário quando a equipe sobe de novo.
- **Supervisor**: lê os limites do Claude (endpoint de uso da conta), do Codex (sessões locais) e
  o saldo da DeepSeek; quando uma ferramenta fica crítica, os implementadores dela param pelo
  roteiro da pausa e a analista muda de ferramenta; quando o limite volta, reabre todo mundo.
  Também acorda quem terminou a vez e ficou parado, e reinicia a sessão de quem não responde.
- **Painel** (`equipe painel`): servidor HTTP em Python puro, só em `127.0.0.1`, com quadro da
  fila (arrastar para reordenar, trocar prioridade), consoles, conversa com a analista, limites,
  carga da máquina, artefatos (prints e relatórios dos agentes) e botão de pausa.

## Requisitos

- Linux (usa `/proc`, `ss`, `fuser`, `flock`), `bash`, `python3` ≥ 3.9, `git`, `tmux`.
- [Claude Code](https://docs.anthropic.com/claude-code) (`claude`) e/ou
  [Codex CLI](https://github.com/openai/codex) (`codex`), já autenticados.
- Opcional: `gnome-terminal` (abre uma janela presa à sessão tmux), `zsh` com uma função que
  aponta o Claude Code para a DeepSeek (para os `deep-N`).

## Instalação

```sh
git clone https://github.com/leandrodaf/equipe-agentes.git ~/equipe-agentes
~/equipe-agentes/install.sh        # link de bin/equipe em ~/.local/bin (precisa estar no PATH)
equipe teste                       # testes unitários do motor
```

## Num projeto

```sh
cd meu-repo
equipe iniciar --descricao "API de pedidos em Go + front React"
$EDITOR .equipe/config.env .equipe/projeto.md   # o gate, as portas, o ambiente do dono, a visão
claude                                          # uma vez, para aceitar "confiar nesta pasta"
equipe prompt implementador | less              # confira o que os agentes vão ler
equipe subir N_CLAUDE=2 N_CODEX=1               # analista + 2 Claude + 1 Codex + painel + supervisor
```

O `equipe iniciar` cria:

| arquivo | o quê |
|---|---|
| `.equipe/config.env` | configuração (abaixo); pode ir para o git |
| `.equipe/projeto.md` | **o que os agentes sabem do projeto**: visão e pilares, stack, princípios técnicos, o ambiente do dono (intocável), como subir um ambiente isolado, invariantes para a varredura, lições. Vai no fim do prompt de todos |
| `.equipe/analista.md`, `.equipe/implementador.md` | opcionais: instruções só para aquele papel |
| `.equipe/roteiros/<nome>.md` | opcionais: substituem os roteiros padrão (`roteiros/`) |
| `.equipe/estado/` | estado local (diários, travas, mensagens, prints, logs); posto no `.git/info/exclude` |
| `MELHORIAS.md` | a fila, com o Protocolo (se ainda não existir) |

Comentários HTML (`<!-- … -->`) nos arquivos do projeto não vão para o prompt.

### `.equipe/config.env`

| chave | padrão | para quê |
|---|---|---|
| `PROJETO` | nome da pasta | identifica os agentes (`claude-1@PROJETO`), a sessão tmux e o painel |
| `DESCRICAO` | | uma frase no topo dos prompts |
| `RAMO` | `main` | ramo principal (só fast-forward) |
| `FILA`, `ARQUIVO_FILA` | `MELHORIAS.md`, `MELHORIAS-ARQUIVO.md` | a fila e os itens encerrados |
| `PREFIXO` | `MEL` | prefixo dos IDs (`MEL-001`; branch `claude-1/mel-001`) |
| `CHANGELOG` | `CHANGELOG.md` | onde `equipe changelog` escreve |
| `LIMITE_VIVOS` | `20` | máximo de itens vivos na fila |
| `GATE` | `make verificar` | o comando que o implementador roda verde uma vez antes de entregar |
| `INSTALAR`, `TESTE_RAPIDO` | | preparar uma worktree; como rodar só o teste do que mudou |
| `PUSH` | `1` (o modelo do `iniciar` põe `0`) | a analista dá push do ramo principal (`0`: ninguém dá push) |
| `APP_URL`, `PORTAS_DONO` | | o app do dono, que ninguém derruba |
| `APP_ATIVO`, `APP_SUBIR`, `APP_PARAR` | | comandos: o app está no ar? / subir (no `equipe subir`) / parar (no `equipe parar APP=1`) |
| `PORTAS_ANALISTA`, `PORTAS_IMPLEMENTADOR` | `8090-8099`, `8100-8199` | faixas para os ambientes isolados |
| `PAINEL_PORTA` | `8077` | porta do painel (uma por projeto, se rodar vários) |
| `PAINEL_IP_EXTRA` | | um IP privado a mais para o painel escutar (ex.: o de um túnel até o celular); só aceita conexão da própria máquina |
| `EVIDENCIAS` | `docs/evidencias` | pasta extra de artefatos no painel |
| `VALIDACAO_REGEX` | testes comuns | o que o painel conta como "teste rodando" |
| `N_CLAUDE`, `N_CODEX`, `N_DEEP` | `3`, `3`, `0` | quantos de cada o `equipe subir` abre |
| `CLAUDE_ARGS`, `CODEX_ARGS` | | argumentos extras (ex.: `--model opus`) |
| `DEEP_COMANDO` | `claude-deep` | função do `~/.zshrc` que abre o Claude Code na DeepSeek |

Os valores aparecem nos prompts e roteiros como `{{CHAVE}}` (mais `{{RAIZ}}`, `{{ESTADO}}`,
`{{NOME}}`, `{{PREFIXO_MIN}}`…). `TERMINAL_AGENTES`, `CLAUDE_ARGS`, `CODEX_ARGS`, `N_*` e
`PAINEL_PORTA` também podem vir do ambiente, para uma execução só.

## Comandos

```
equipe subir [N_CLAUDE=3 N_CODEX=3 N_DEEP=0 PRIMEIRO=1]   tudo: app, analista, implementadores, painel, supervisor
equipe agentes <claudes> <codex> [analista 0|1] [primeiro] abre só esses (DEEP_N=N para DeepSeek)
equipe painel | supervisor | limites
equipe pausar "motivo" | retomar | pausa ver | parar [APP=1]
equipe itens [STATUS|fila] · trava · msg · vivo · arvore · recuperar · limpar-worktrees
equipe prompt <papel> [nome] · roteiro <nome> · faxina · info
```

`equipe ajuda` lista tudo. Os próprios agentes usam os mesmos comandos (o `equipe` vai no PATH de
cada sessão e acha o projeto de qualquer worktree dele).

## Estrutura

```
bin/equipe          o comando
lib/                config.py (fonte única da configuração), comum.sh, identidade.py, prompt.py,
                    abrir.sh, msg.sh, trava.sh, pausa.sh, parar.sh, supervisor.py, limites.py, …
painel/             servidor.py + index.html (sem dependências)
prompts/            analista.md, implementador.md: o protocolo genérico de cada papel
roteiros/           faxina, varredura, pesquisa (passos longos da analista)
modelos/            o que o `equipe iniciar` copia para o projeto
testes/             unitários (`equipe teste`) e e2e-supervisor.sh (abre sessões reais)
```

## Testes

`equipe teste` roda os unitários num projeto descartável. `testes/e2e-supervisor.sh`, rodado de
dentro de um projeto de teste com a equipe parada, abre sessões **reais** (gasta um pouco de limite)
e confere cada decisão do supervisor com limites falsos.

## Licença

MIT.
