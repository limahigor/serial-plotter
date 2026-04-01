# Documentação do Senamby

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](../en/index.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](index.md)

## Visão Geral

Senamby é uma aplicação desktop para operar plantas usando plugins reutilizáveis. Uma planta combina:

- sensores
- atuadores
- um plugin de driver
- zero ou mais plugins de controlador

A aplicação permite definir plantas, conectá-las a uma runtime ao vivo, acompanhar gráficos em tempo real, exportar dados da sessão e analisar arquivos JSON exportados no modo offline.

## Para Quem É

- operadores que configuram plantas e executam testes
- integradores que criam drivers para dispositivos e protocolos
- engenheiros de controle que criam controladores e bindings

## Módulos Principais da Aplicação

- **Plotter**: cria plantas, conecta runtimes, acompanha telemetria, exporta CSV/JSON e gerencia controladores
- **Analyzer**: abre JSONs exportados da planta para análise offline de sensores, setpoints e atuadores vinculados
- **Plugins**: cria, importa, edita, inspeciona e remove plugins reutilizáveis de driver/controlador

## Mapa da Documentação

- [Primeiros Passos](getting-started.md)
- [Conceitos Centrais](core-concepts.md)
- [Plantas](plants.md)
- [Drivers e Controladores](drivers-and-controllers.md)
- [Formato de Arquivo de Plugin](plugin-file-format.md)
- [Comportamento da Runtime](runtime-behavior.md)
- [Solução de Problemas](troubleshooting.md)

## Ordem Recomendada de Leitura

1. [Primeiros Passos](getting-started.md)
2. [Conceitos Centrais](core-concepts.md)
3. [Plantas](plants.md)
4. [Drivers e Controladores](drivers-and-controllers.md)
5. [Formato de Arquivo de Plugin](plugin-file-format.md)
6. [Comportamento da Runtime](runtime-behavior.md)
7. [Solução de Problemas](troubleshooting.md)

## Fluxo Comum Passo a Passo

1. Abrir o módulo `Plugins` e criar ou importar um driver
2. Opcionalmente criar ou importar um ou mais controladores
3. Abrir o módulo `Plotter` e criar uma planta
4. Adicionar variáveis, atribuir o driver e preencher a configuração do plugin
5. Adicionar controladores, fazer bindings de sensores e atuadores e salvar
6. Conectar a planta e aguardar a telemetria ao vivo
7. Ajustar setpoints, pausar/retomar a plotagem quando necessário e exportar os dados
8. Abrir o módulo `Analyzer` para inspecionar os JSONs exportados
