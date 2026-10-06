<!--
Contexto do projeto para TODOS os agentes. Vai no fim do prompt de cada um, depois do protocolo
genérico, e vale mais do que ele quando os dois divergem. Escreva para alguém sênior que nunca viu
o projeto. Os {{VALORES}} do config.env são preenchidos (ex.: {{RAIZ}}, {{RAMO}}, {{PREFIXO}}).
Para instruções só da analista ou só dos implementadores: .equipe/analista.md e .equipe/implementador.md.
Apague estes comentários quando terminar.
-->

## O que é

<!-- Uma ou duas frases: o produto, para quem, e a stack (linguagens, frameworks, banco). -->

## A visão e os pilares

<!--
O que o produto quer ser e os 3 a 5 pilares que todo item tem de servir (a analista usa isto para
decidir o que propor). Ex.: "1. Confiável: todo número bate com a fonte. 2. Rápido: …".
Inclua as perguntas que o dono faz ao produto, em ordem de frequência.
-->

## Referências

<!-- Produtos concorrentes ou de referência que valem uma olhada, e normas que se aplicam. -->

## Princípios técnicos

<!--
O que o código deste projeto exige: arquitetura, convenções, o que o lint reprova, como lidar com
dinheiro/datas/fuso, migrações de banco (como numerar), padrão de mensagem de commit.
-->

## O ambiente do dono (intocável)

<!--
O que está no ar de verdade (app, banco, serviços), em que portas, e como o dono sobe/desce.
Diga o que os agentes NUNCA podem fazer aqui (gravar no banco real, reiniciar o serviço…), e o que
podem só ler. Se o app recarrega sozinho quando algo entra no {{RAMO}}, diga e diga como conferir.
-->

## Ambiente isolado (para implementar e revisar)

<!--
Passo a passo para um agente subir o produto da worktree dele sem tocar no do dono:
dados (cópia do banco, fixtures), servidor (porta da faixa dele), front. Inclua como derrubar e
apagar tudo no fim, e como conferir que não está apontando para os dados reais.
Implementadores: portas {{PORTAS_IMPLEMENTADOR}}; analista: {{PORTAS_ANALISTA}}.
-->

## Varredura

<!--
Opcional: a lista de telas/módulos em ordem de importância, o comando de uma passada automática
(se houver) e a tabela de invariantes (I1, I2…: dois lugares que precisam dar o mesmo resultado).
-->

## Lições deste projeto

<!-- Cada linha veio de um erro real aqui; a equipe acrescenta (pela analista, com o dono). -->
