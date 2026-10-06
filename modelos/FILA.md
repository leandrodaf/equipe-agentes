# Fila de itens — {{PROJETO}}

Este arquivo é o canal entre a analista e os implementadores:

- **Analista** (escreve as propostas, não implementa): simula o uso, mede, pesquisa e valida a
  entrega.
- **Implementador** (implementa): pega um item, marca que está trabalhando, entrega e pede revisão.

Ninguém apaga o que o outro escreveu. Tudo é acrescentado no **Registro** do item. A única exceção
é o arquivamento (regra 8).

## Protocolo

### Estados (campo `Status`)

| estado | quem define | significado |
|---|---|---|
| `PROPOSTO` | analista | pronto para ser pego |
| `EM ANDAMENTO` | implementador | alguém está trabalhando; ninguém mais mexe |
| `PRONTO PARA REVISÃO` | implementador | entregue; a analista valida contra os critérios de aceitação |
| `AJUSTE NECESSÁRIO` | analista | a revisão encontrou algo; o motivo está no Registro |
| `APROVADO` | analista | todos os critérios de aceitação conferidos |
| `INTEGRADO em <hash>` | implementador | merge concluído; a analista confere e arquiva no mesmo ciclo |
| `AGUARDANDO O DONO` | analista | depende de informação ou conferência exclusiva do dono |
| `DESCARTADO` | analista | não vale a pena (motivo no Registro) |

Fluxo: `PROPOSTO → EM ANDAMENTO → PRONTO PARA REVISÃO → APROVADO → INTEGRADO`
(ou `→ AJUSTE NECESSÁRIO → EM ANDAMENTO → …`).

### Avisos em vigor

- **Travas:** `fila` para editar este arquivo; `integracao` para alterar o `{{RAMO}}`. Confira `OK`
  antes de prosseguir; passos dependentes com `&&`, nunca `;`. Sem stash nem force push.

### Regras

1. Pegue **um item por vez**, na ordem de prioridade (P0 antes de P1…) e na ordem do dono no
   painel (`equipe itens fila`), a não ser que o item diga que depende de outro.
2. Ao pegar: mude `Status` para `EM ANDAMENTO`, acrescente `- Responsável: <nome>` e, no Registro,
   `- AAAA-MM-DD HH:MM · <nome> · iniciado`.
3. Ao entregar: mude para `PRONTO PARA REVISÃO` e acrescente no Registro o **commit**, os arquivos
   tocados e, para cada critério de aceitação, como ele foi atendido (teste, print, comando).
4. Se discordar de uma proposta, não a ignore: escreva o argumento no Registro e deixe em
   `PROPOSTO`; a analista responde.
5. Critérios de aceitação são o contrato. "Parece bom" não aprova; cada critério é conferido um a
   um.
6. **Aprovado não é entregue ao dono até estar no `{{RAMO}}`.** Quem implementou integra **logo
   após o APROVADO** (antes de pegar outro item), registra `integrado em <hash>` e muda o Status
   para `INTEGRADO em <hash>`. A analista confere, dá o push (se o projeto usa) e arquiva no mesmo
   ciclo.
7. O gate do projeto (`{{GATE}}`) roda verde uma vez na entrega; integração com rebase limpo não
   repete teste.
8. **Arquivamento (analista).** Itens `INTEGRADO em <hash>` e `DESCARTADO` saem deste arquivo e
   vão, com o texto completo, para o `{{ARQUIVO_FILA}}`. Aqui fica só uma linha em "Concluídos". A
   analista também remove notas que ficaram velhas, para este arquivo mostrar só o que está vivo.

### Formato de um item

```
## {{PREFIXO}}-NNN · Título curto
- Status: PROPOSTO
- Prioridade: P0 (errado/enganoso) · P1 (alto impacto) · P2 (melhoria) · P3 (polimento)
- Área: <área do produto>
- Depende de: {{PREFIXO}}-XXX (opcional)

**Problema.** O que está errado hoje, com evidência (arquivo:linha, número medido).
**Fundamento.** Por que importa — pesquisa, norma ou prática consolidada, com referência.
**Proposta.** O que fazer (o quê, não o como detalhado; o implementador decide o como).
**Critérios de aceitação.** Lista verificável.
**Fora de escopo.** O que não fazer agora.
**Registro.** Linhas datadas de todos os agentes.
```

---

## Fila recomendada (mantida pela analista)

## Ideias ainda não detalhadas (≤ 15 linhas)

## Concluídos (arquivados)
