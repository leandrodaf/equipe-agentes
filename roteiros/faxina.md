# Roteiro: faxina (passo 4 do ciclo da analista)

**Quando:** o diário não tem `faxina <data de hoje>`, ou você arquivou 3 ou mais itens desde a
última. **Por quê:** a fila ({{FILA}}) é lida inteira por todos os agentes, várias vezes por hora;
cada linha morta ali é paga por cada agente, a cada leitura. O resto (portas, prints, ambientes de
teste) é disco e memória que os agentes dividem.

## 1. O relatório (só lê; nunca apaga nada)

```
equipe faxina --curto
```

Ele confere as condições (máquina ligada há ≥ 30 min, gate rodando, carga) e lista, por seção,
**o que pode sair, o motivo e o comando**: o tamanho da fila, a contagem de vivos, as Ideias acima
de 15 linhas, rodadas e seções encerradas, `Depende de` que aponta para item arquivado, Concluídos
com hash fora do `{{RAMO}}`, idade do último backup, servidores esquecidos nas portas dos agentes,
prints de itens arquivados, diários e logs grandes, e backups fora da retenção.

Limpeza própria do projeto (cópias de banco, containers, caches) está no `.equipe/projeto.md`,
se houver: faça junto, com o mesmo critério de "abandonado".

**Abandonado**, para o relatório, é: item arquivado; ou agente parado **e** diário sem linha há
mais de 3 h **e** equipe fora de pausa (`{{ESTADO_REL}}/PAUSA`). Com a equipe em pausa, nada de
item vivo é recolhido: os implementadores voltam e continuam dali.

## 2. Você executa, uma linha de cada vez

Leia o motivo de cada `→` e rode o comando sugerido só se concordar. Nunca rode a lista inteira
de uma vez nem junte comandos com `;` (use `&&` ou um por vez).

**A fila** (com a trava `fila` e depois do backup; o relatório não edita):

- **Rodada encerrada** (nenhum item vivo abaixo dela): copie o cabeçalho e o contexto para o fim
  do `{{ARQUIVO_FILA}}` com a linha "contexto da Rodada N, arquivado em AAAA-MM-DD", confira com
  `grep`, e só então tire da fila. Conhecimento que ainda serve (base de pesquisa, por exemplo) fica.
- **Ideias acima de 15 linhas:** para cada uma, decida uma de três: **vira item** (tem evidência e
  cabe no limite), **sai** (velha, fraca ou já resolvida por outro item: uma linha no diário com o
  motivo) ou **fica**. Comece pela mais velha.
- **`Depende de` cumprido:** tire da linha o item já arquivado (mantenha os vivos).
- **Fila recomendada** coerente com as prioridades e com a ordem do dono no painel.
- Meta de tamanho: **≤ 700 linhas**. O maior peso morto costuma ser a lista de **Concluídos**:
  deixe ali só as **15 mais recentes** e mova as outras, na mesma ordem, para uma seção
  `## Índice de concluídos` no **início** do `{{ARQUIVO_FILA}}` (a única parte daquele arquivo que
  pode receber linhas no meio). Confira a contagem antes e depois (`grep -c '^- {{PREFIXO}}-'`).
  O Registro de um item vivo nunca se resume: ele é dos implementadores (só acrescente).
- Item novo nunca reaproveita número.

**Worktrees e branches:** só `equipe limpar-worktrees --apagar`. O que ele mantiver com item
arquivado ou descartado: anote no diário para o dono decidir. Nunca toque no `{{RAMO}}`,
`resgate/*` nem em branch de item vivo.

**Backups:** a retenção é **tudo das últimas 48 h + o último de cada dia por 30 dias**, só para
as pastas `AAAA-MM-DD-HHMM`. Outros arquivos na mesma pasta são do dono: não apague.

**Diários grandes** (> 500 linhas): mova as mais antigas para
`{{ESTADO_REL}}/diarios-antigos/<nome>-AAAA-MM.md` e deixe as últimas 100. O seu diário segue a
mesma regra, mas copie antes as linhas de varredura e de `faxina` dos últimos 7 dias para o fim:
são o ponto de retomada e o gatilho deste roteiro.

## 3. Feche

- Uma linha no diário: `faxina AAAA-MM-DD: <linhas da fila antes → depois>, <o que saiu>,
  <o que ficou para o dono>`. Se a fila cresce faxina após faxina, o problema é a escrita dos
  itens: escreva itens e Registros mais curtos.
- Se o relatório errou (apontou algo que não devia, ou deixou passar), proponha a correção do
  `roteiros/faxina.py` ao dono em vez de lembrar da exceção.
