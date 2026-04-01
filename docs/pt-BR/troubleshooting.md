# Solução de Problemas

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](../en/troubleshooting.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](troubleshooting.md)

## Plugin Não Encontrado

Sintomas:

- a conexão falha
- a planta abre, mas não consegue rodar
- a planta importada referencia um plugin que não está disponível

O que verificar:

- o plugin existe no workspace
- o `id` ou nome do plugin ainda corresponde ao salvo na planta
- o arquivo-fonte e o registry do plugin não foram apagados manualmente
- o catálogo de plugins foi recarregado com sucesso

## Erros de Contrato de Controlador

Sintomas comuns:

- a validação do controlador falha
- a conexão falha com erro Python
- a atualização do controlador falha após salvar

Causas comuns:

- usar `context["controller"]` em vez de `context.controller`
- usar `self.context.controller.params["kp"]["value"]` em vez de `.value`
- retornar ids de atuador que não pertencem ao binding do controlador
- esquecer que `snapshot["controller"]` é um dicionário, enquanto `self.context.controller` é um objeto

## Controlador `pending_restart`

Significa que:

- o controlador foi salvo
- a runtime atual não consegue aplicá-lo imediatamente

Como resolver:

1. salve o controlador
2. desconecte a planta
3. reconecte a planta

## Não Foi Possível Remover Controlador Ativo

Se um controlador estiver ativo e sincronizado em uma planta rodando, a remoção é bloqueada.

Como resolver:

1. desative o controlador
2. salve a configuração da planta/controlador
3. remova o controlador

## Problemas com Dependências Python

Se a runtime não iniciar por causa das dependências:

- revise a lista de dependências do driver/controlador
- reconecte a planta depois de corrigir a definição do plugin
- inspecione o ambiente gerado em `Documents/Senamby/workspace/envs/`

## "Mensagem Inválida Recebida do Driver"

Sintoma típico:

- a runtime informa que o driver enviou dados inválidos para o protocolo

O que isso significa:

- o backend esperava JSON lines no canal de protocolo do runner
- algum texto chegou nesse caminho de forma inesperada

Comportamento atual:

- `print()` Python é redirecionado para fora do `stdout` de protocolo
- saída comum de `stdout` de bibliotecas nativas também é desviada para `stderr`

Se ainda acontecer:

- prefira logar em `stderr`
- evite escrever manualmente em `stdout`
- investigue bibliotecas nativas que possam bypassar completamente os handles padrão do processo

## Sem Dados Úteis para Exportar ou Analisar

Se a exportação CSV/JSON ou o Analyzer parecerem vazios:

- confirme que a planta ficou conectada por tempo suficiente para coletar amostras
- confirme que a telemetria ao vivo estava chegando ao plotter
- no Analyzer, carregue o JSON exportado pelo Senamby, não um JSON arbitrário

## Planta Fechada vs Removida

Se uma planta sumiu da sessão:

- ela pode ter sido apenas fechada, e não apagada
- plantas fechadas continuam salvas e podem ser abertas/importadas novamente
- plantas removidas apagam o registry persistido do workspace
