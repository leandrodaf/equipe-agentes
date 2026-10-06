# Roteiro: varredura (passo 5 do ciclo da analista)

A varredura procura o que ninguém pediu para olhar. Ela tem **três camadas**, de propósito em
ordem de custo: a máquina mede o que é medível (camada 1), você confere as regras que só um
especialista confere (camada 2), e usa o produto como o dono usaria (camada 3). Na prática, **a
camada 1 acha polimento; os P0 saem da camada 2.** Gaste a atenção onde ela rende.

O que é específico do projeto (a lista de telas ou módulos, o comando da passada automática, a
tabela de invariantes) está no `.equipe/projeto.md` ou num `.equipe/roteiros/varredura.md`
próprio, que substitui este.

## Antes de começar

1. **Retome, não recomece.** `grep -n 'varredura' {{ESTADO_REL}}/analista.md | tail -3`: se há uma
   varredura aberta, continue da camada e do ponto anotados.
2. **Onde:** medir e ler pode ser no ambiente do dono, se o projeto disser que é seguro. Clique
   que grava, formulário e qualquer escrita: só no seu ambiente isolado.
3. **Ordem: o que mudou primeiro.** Desde a última varredura (data no diário):
   `git log --since=<data> --name-only --format= {{RAMO}} | sort | uniq -c | sort -rn | head -15`.
   O que mudou vem antes; entre o que não mudou, o que mais importa ao dono vem antes do enfeite.

## Camada 1 · a passada automática

Se o projeto tem uma passada automática (o comando está no `.equipe/projeto.md`), rode-a: ela mede
o que é medível (tamanho de página, rolagem lateral, lentidão, erros HTTP e de console,
acessibilidade, texto quebrado como `NaN`/`undefined`) e diz **o que piorou desde a passada
anterior**. Regressão de um item recém-integrado volta para ele (não é item novo).

Sem passada automática, faça à mão o mínimo: abra cada tela ou rode cada comando principal em
duas larguras (desktop e celular) ou com as entradas mais comuns, e anote o que falha.

Leia cada ✘ antes de acreditar nele: a passada é um detector, não um juiz. Confirme com uma
segunda medida ou um print **antes** de virar item.

## Camada 2 · as regras fecham (aqui moram os P0)

Cada linha da tabela de **invariantes** do projeto (no `.equipe/projeto.md`) diz que dois lugares
que mostram a mesma coisa precisam dar o mesmo resultado (o mesmo total em duas telas, o mesmo
estado em duas fontes, a mesma regra em dois módulos). Confira pela fonte (API só leitura,
consulta só leitura, arquivo), não pela tela; a tela só confirma o rótulo. Anote no diário
`I<n> ✔` ou `I<n> ✘ {{PREFIXO}}-NNN`; invariante quebrada é **P0**.

Quando um P0 nascer de uma regra que não está na tabela, **proponha ao dono acrescentar a linha**:
a tabela é a memória do que já quebrou e deve crescer.

Cruze também **no tempo**: um resultado passado (um mês fechado, um relatório antigo) não pode
mudar entre duas varreduras sem uma explicação.

## Camada 3 · usar como o dono

Por tela ou fluxo, na largura em que o dono mais usa:

1. **A pergunta da tela.** Cada tela existe para responder uma pergunta. Abra e, sem rolar,
   responda em 5 segundos. Se não der, é P1.
2. **Rastreabilidade:** escolha **um** número ou estado da tela e tente chegar à origem dele.
   Conte os passos; o que não leva a nada é item.
3. **Formulários,** só no seu ambiente: vazio, zero, negativo, gigante, vírgula × ponto, data
   inválida, texto longo, duplo clique no salvar, recarregar e conferir que ficou. Mensagem clara
   que diz o que fazer.
4. **Texto:** jargão, a mesma coisa com dois nomes, número sem comparação, frase que o dono não
   entenderia.
5. **Cada elemento clicável:** botão, aba, filtro, ordenação, menu, paginação, "ver mais"; e os
   fluxos: abrir, filtrar, voltar, recarregar no meio. Localize por texto, nunca por índice.

**Sinais do próprio dono:** cada correção manual que ele faz é um defeito que o produto deixou
para ele. Se o projeto guarda essas correções, olhe uma vez por varredura (só leitura).

## O que fazer com o que achar

- **Antes de escrever:** `grep -n '<palavra>' {{FILA}} {{ARQUIVO_FILA}}`. Já existe vivo → acrescente a
  evidência no Registro dele. Já foi arquivado e voltou → item novo que cita o antigo, com
  "regressão" no título.
- **Agrupe:** problemas pequenos da mesma tela viram um item só; o mesmo problema em várias telas
  vira um item de componente.
- **Prioridade:** invariante quebrada = P0; pergunta da tela sem resposta, quebra no celular ou
  falha séria de acessibilidade = P1; texto, altura e alvo = P2/P3.
- Limite de itens vivos cheio: uma linha em "Ideias ainda não detalhadas" e siga.

**Diário, uma linha por tela** (é o seu ponto de retomada):
`varredura N · <tela> · c1 ✔ · I1 ✔ I2 ✘ {{PREFIXO}}-NNN · pergunta ✔ · rastreio 3 passos · formulário ✔ texto ✘ (ideia)`.
Ao fechar todas: `varredura N completa · AAAA-MM-DD · itens: … · nada em: …`.
