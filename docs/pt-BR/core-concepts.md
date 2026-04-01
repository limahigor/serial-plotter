# Conceitos Centrais

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](../en/core-concepts.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](core-concepts.md)

## Planta

Uma planta é a unidade principal de execução no Senamby. Ela agrupa:

- variáveis
- uma instância de driver
- zero ou mais instâncias de controlador
- tempo de amostragem
- estado de sessão ao vivo, como conectado, pausado, estatísticas e status de runtime

No uso diário, a planta é o objeto que você abre, conecta, monitora, exporta, fecha e remove no módulo `Plotter`.

## Variável

Uma variável descreve um sinal da planta.

- `sensor`: valor medido do processo, normalmente exibido com PV e SP
- `atuador`: valor de saída, normalmente exibido como variável manipulada

Observação importante:

- a UI pública fala em atuadores
- o valor persistido do tipo continua sendo `atuador`

Cada variável possui:

- `id`
- `name`
- `unit`
- `setpoint`
- `pv_min`
- `pv_max`
- `linked_sensor_ids` opcionais para relacionar atuadores a sensores

## Plugin de Driver vs Instância de Driver

Um **plugin de driver** é a definição reutilizável armazenada no catálogo de plugins.

Uma **instância de driver** é o plugin selecionado junto com a configuração anexada a uma planta.

O driver é responsável por:

- abrir e fechar conexões externas
- ler sensores
- opcionalmente ler feedback de atuadores
- escrever saídas de atuador quando há controladores ativos
- converter unidades cruas do dispositivo para as unidades públicas da planta

Em runtime, o driver recebe:

- `context.config`
- `context.plant`

Métodos obrigatórios:

- `connect()`
- `stop()`
- `read()`

`write(outputs)` passa a ser obrigatório quando a planta possui controladores ativos.

## Plugin de Controlador vs Instância de Controlador

Um **plugin de controlador** é o algoritmo de controle reutilizável armazenado no catálogo de plugins.

Uma **instância de controlador** é o controlador configurado dentro de uma planta, incluindo:

- estado de ativação
- bindings de entrada
- bindings de saída
- valores de parâmetros
- status de runtime

Em runtime, o controlador recebe:

- `context.controller`
- `context.plant`

Método obrigatório:

- `compute(snapshot)`

Status atuais exibidos na aplicação:

- `synced`: a configuração salva já está aplicada na runtime rodando
- `pending_restart`: a configuração foi salva, mas a runtime precisa reconectar antes de usá-la

## Runtime

A runtime só existe enquanto a planta está conectada. Ela executa o ciclo:

`read -> control -> write -> publish`

O frontend não executa esse loop. O frontend apenas reage a eventos de status e telemetria emitidos pelo backend.

Regras importantes de sessão:

- conectar inicia a runtime
- desconectar encerra a runtime, mas mantém a planta aberta na sessão
- pausar pausa só a plotagem na UI; a runtime continua rodando
- fechar descarrega a planta da sessão
- remover apaga o registry persistido

## Hot Update

Enquanto a planta está conectada, o Senamby pode tentar aplicar mudanças de controlador ao vivo.

Resultados típicos:

- mudanças de parâmetro ou binding podem ser aplicadas imediatamente
- mudanças sensíveis ao ambiente podem virar `pending_restart`
- remoção de controlador ativo e sincronizado é bloqueada até ele ser desativado

## Workspace

O workspace é a área persistente de armazenamento para:

- plugins
- plantas
- ambientes Python
- artefatos de bootstrap/sessão da runtime

Por padrão ele fica em:

`Documents/Senamby/workspace`

Diferença importante:

- o workspace é a persistência oficial
- a sessão atual contém apenas as plantas carregadas na UI
- plantas persistidas não são reabertas automaticamente no startup

## Exportação e Analyzer

Sessões ao vivo do plotter podem ser exportadas como:

- CSV para planilhas ou scripts
- JSON para replay estruturado no Analyzer

O Analyzer é um módulo offline. Ele lê JSONs exportados e reconstrói as séries de sensores, setpoints e atuadores vinculados sem conectar a uma runtime ao vivo.
