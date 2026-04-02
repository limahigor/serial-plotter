# Comportamento da Runtime

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](../en/runtime-behavior.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](runtime-behavior.md)

## Fluxo de Conexão

Quando uma planta conecta, o backend:

1. resolve o driver salvo e os controladores ativos
2. atualiza metadados de plugin a partir do workspace quando necessário
3. prepara ou reutiliza o ambiente Python
4. monta um bootstrap compacto
5. inicia o runner Python
6. aguarda o handshake `ready` e `connected`
7. começa a encaminhar status e telemetria ao vivo para o frontend

## Canais de Comunicação da Runtime

O processo da runtime usa três canais:

- `stdin`: comandos do Rust para o runner
- `stdout`: protocolo interno JSON do runner de volta para o Rust
- `stderr`: logs, tracebacks e saída nativa redirecionada

Comportamento importante:

- o runner reserva `stdout` para o tráfego do protocolo JSON
- o runner duplica o descritor original de `stdout` para escrever o protocolo
- `print()` em Python vai para `stderr`
- saída comum de `stdout` de bibliotecas nativas também é desviada para `stderr`
- `context.logger` em drivers/controladores emite logs estruturados para o módulo Console

## Regras da Runtime ao Vivo

- a runtime só existe enquanto a planta estiver conectada
- plantas não são recarregadas automaticamente no startup
- controladores podem ser atualizados ao vivo enquanto a planta está conectada
- algumas mudanças exigem reconexão e viram `pending_restart`

## Ciclo `read -> control -> write -> publish`

### 1. Read

O runner chama `driver.read()` e espera:

```json
{
  "sensors": { "sensor_1": 58.2 },
  "actuators": { "actuator_1": 37.0 }
}
```

### 2. Control

Para cada controlador ativo, o runner monta um snapshot com:

- `dt_s`
- `setpoints`
- `sensors`
- `actuators`
- `variables_by_id`
- `controller`

Depois chama `compute(snapshot)` e recebe:

```json
{
  "actuator_1": 42.0
}
```

### 3. Write

O runner consolida as saídas do ciclo e chama:

```python
driver.write(outputs)
```

### 4. Publish

O runner publica telemetria para o backend, que a encaminha ao frontend como `plant://telemetry`.

## Backlog do Pause

Pause não interrompe o loop da runtime. O frontend para de plotar temporariamente e acumula backlog de telemetria. Ao retomar, a fila acumulada é reaplicada aos gráficos.

Isso significa:

- o controle continua rodando
- leituras e escritas do driver continuam acontecendo
- apenas a renderização dos gráficos é pausada na UI

## Telemetria e Plotagem

O backend emite eventos achatados `plant://telemetry` para o frontend.

Regra importante de plotagem:

- os gráficos de atuador usam atualmente o readback de atuador presente na telemetria
- eles não usam o payload bruto de escrita como valor principal exibido

A telemetria pode incluir campos como:

- `cycle_id`
- `configured_sample_time_ms`
- `effective_dt_ms`
- `cycle_duration_ms`
- `read_duration_ms`
- `control_duration_ms`
- `write_duration_ms`
- `publish_duration_ms`
- `cycle_late`
- `late_by_ms`
- `sensors`
- `actuators`
- `actuators_read`
- `setpoints`
- `controller_outputs`
- `written_outputs`

## Hot Update e `pending_restart`

Quando a configuração de controlador muda com a planta conectada:

- o Senamby tenta carregar o conjunto atualizado ao vivo
- se a runtime/ambiente atual aceitar a mudança, o status permanece `synced`
- se a mudança exigir rebuild do ambiente ou reconexão, o status vira `pending_restart`

Correção típica para `pending_restart`:

1. salvar a mudança do controlador
2. desconectar a planta
3. reconectar a planta

## Arquivos de Runtime

Os dados persistentes do workspace ficam em:

- `drivers/`
- `controllers/`
- `plants/`
- `envs/`

Sessões conectadas também usam:

- `runtimes/<runtime_id>/bootstrap.json`

O script Python do runner fica na área compartilhada de runtimes e é reutilizado entre sessões.

## Notas de Debug

- erros e logs Python chegam por `stderr`
- o backend ecoa linhas de `stderr` com o prefixo `driver-runtime`
- logs estruturados de driver/controlador também são encaminhados para o Console
- se uma biblioteca nativa bypassar completamente os handles do processo, ainda existe possibilidade teórica de corrupção do protocolo, mas esse deixou de ser o caso comum para saídas estilo `printf`
