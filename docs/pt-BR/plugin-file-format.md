# Formato de Arquivo de Plugin

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](../en/plugin-file-format.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](plugin-file-format.md)

## O que este guia cobre

Use este documento quando quiser:

- criar um plugin do zero
- importar um plugin via JSON
- entender o contrato Python usado em runtime
- saber quais dados o driver ou controlador recebe

## Runtime suportada

O caminho oficial de execução hoje é **Python**.

Observação importante:

- o importador JSON consegue fazer parse de `runtime: "rust-native"`
- o fluxo suportado de criação e execução para usuários finais ainda é Python

## Forma do JSON de Plugin

O Senamby aceita arquivos JSON de plugin com esta forma comum:

```json
{
  "name": "Meu Driver",
  "kind": "driver",
  "runtime": "python",
  "entryClass": "MeuDriver",
  "sourceFile": "main.py",
  "schema": [
    {
      "name": "port",
      "type": "string",
      "description": "Porta serial"
    },
    {
      "name": "baudrate",
      "type": "int",
      "defaultValue": 115200,
      "description": "Baud rate serial"
    }
  ],
  "dependencies": [
    {
      "name": "pyserial",
      "version": ""
    }
  ],
  "description": "Driver serial para um dispositivo de teste",
  "version": "1.0.0",
  "author": "Seu Nome"
}
```

Aliases aceitos na importação:

- `kind` ou `type`
- `entryClass` ou `entry_class`
- `sourceFile` ou `source_file`
- `defaultValue` ou `default_value`

## Kinds e Tipos de Campo Suportados

Kinds suportados:

- `driver`
- `controller`

Tipos de campo de schema:

- `bool`
- `int`
- `float`
- `string`
- `list`

Campos de schema podem opcionalmente definir:

- `defaultValue`
- `description`

## Criando um plugin pela UI

Passo a passo:

1. Abra o módulo `Plugins`
2. Escolha `Driver` ou `Controller`
3. Crie um plugin novo ou importe um arquivo JSON
4. Preencha:
   - nome
   - runtime `python`
   - classe de entrada
   - arquivo-fonte
   - campos de schema
   - dependências Python opcionais
5. Salve o plugin
6. Anexe esse plugin a uma planta no módulo `Plotter`

## Contrato Python de Driver

```python
from typing import Any, Dict

class MeuDriver:
    def __init__(self, context: Any) -> None:
        self.context = context

    def connect(self) -> bool:
        return True

    def stop(self) -> bool:
        return True

    def read(self) -> Dict[str, Dict[str, float]]:
        return {
            "sensors": {"var_0": 0.0},
            "actuators": {"var_2": 0.0}
        }

    def write(self, outputs: Dict[str, float]) -> bool:
        return True
```

O contexto público do driver expõe apenas:

- `context.config`
- `context.plant`
- `context.logger`

### Como pensar no `context` do driver

- `context.config` contém os valores atuais da configuração do driver
- essas chaves vêm do `schema` do plugin
- exemplo: `self.context.config.get("port")`
- `context.plant` contém a estrutura pública da planta já normalizada pela runtime
- `context.logger` envia logs estruturados para o módulo `Console`

### Estrutura de `context.plant`

Dentro de driver e controlador, `context.plant` expõe:

- `context.plant.id`
- `context.plant.name`
- `context.plant.variables`
- `context.plant.variables_by_id`
- `context.plant.sensors`
- `context.plant.actuators`
- `context.plant.setpoints`

Leituras úteis:

- ids de sensores: `self.context.plant.sensors.ids`
- ids de atuadores: `self.context.plant.actuators.ids`
- setpoint atual de um sensor: `self.context.plant.setpoints.get(sensor_id, 0.0)`
- metadado de variável: `self.context.plant.variables_by_id[sensor_id].unit`

Cada variável em `context.plant.variables` ou `context.plant.variables_by_id[...]` expõe:

- `.id`
- `.name`
- `.type`
- `.unit`
- `.setpoint`
- `.pv_min`
- `.pv_max`
- `.linked_sensor_ids`

Cada grupo `context.plant.sensors` e `context.plant.actuators` expõe:

- `.ids`
- `.count`
- `.variables`
- `.variables_by_id`

### Como usar `context.logger`

Você pode emitir logs estruturados assim:

- `self.context.logger.debug("mensagem", {"chave": valor})`
- `self.context.logger.info("mensagem", {"chave": valor})`
- `self.context.logger.warning("mensagem", {"chave": valor})`
- `self.context.logger.error("mensagem", {"chave": valor})`

### Regras do payload de `read()`

`read()` deve retornar um objeto com dois mapas:

```json
{
  "sensors": {
    "sensor_1": 58.2
  },
  "actuators": {
    "actuator_1": 37.0
  }
}
```

Regras práticas:

- as chaves devem ser ids de variáveis da planta
- os valores devem ser numéricos finitos
- ausência de `sensors` ou `actuators` é tratada como `{}`
- chaves desconhecidas são ignoradas

### Regras do payload de `write(outputs)`

Quando existir saída de controlador no ciclo, a runtime chama:

```python
write(outputs)
```

`outputs` tem este formato:

```json
{
  "actuator_1": 42.0,
  "actuator_2": 15.5
}
```

Esses valores já estão no espaço de unidades públicas da planta.

## Contrato Python de Controlador

```python
from typing import Any, Dict

class MeuControlador:
    def __init__(self, context: Any) -> None:
        self.context = context

    def compute(self, snapshot: Dict[str, Any]) -> Dict[str, float]:
        kp = self.context.controller.params["kp"].value
        sensor_id = self.context.controller.input_variable_ids[0]
        actuator_id = self.context.controller.output_variable_ids[0]
        pv = snapshot["sensors"].get(sensor_id, 0.0)
        sp = snapshot["setpoints"].get(sensor_id, 0.0)
        erro = sp - pv
        return {actuator_id: kp * erro}
```

O contexto público do controlador expõe apenas:

- `context.controller`
- `context.plant`
- `context.logger`

### Regra mental: `context` vs `snapshot`

Use esta regra simples:

- `context` = dados públicos estáveis do plugin naquele momento
- `snapshot` = fotografia serializada do ciclo atual

Na prática:

- leia parâmetros normalmente por `self.context.controller.params["kp"].value`
- leia sinais dinâmicos por `snapshot["sensors"]`, `snapshot["setpoints"]` e `snapshot["actuators"]`
- use `snapshot["controller"]` quando você precisar da versão serializada do controlador dentro do ciclo

Diferença importante:

- `self.context.controller` é um objeto com atributos
- `snapshot["controller"]` é um dicionário serializado

Isso significa:

- use `self.context.controller.params["kp"].value`
- não assuma `self.context["controller"]`
- não assuma `self.context.controller.params["kp"]["value"]`

## Estrutura de `context.controller`

Dentro do controlador, `self.context.controller` expõe:

- `id`
- `name`
- `controller_type`
- `input_variable_ids`
- `output_variable_ids`
- `params`

Cada entrada em `params` expõe:

- `.key`
- `.type`
- `.value`
- `.label`

Exemplos diretos:

- ganho proporcional: `self.context.controller.params["kp"].value`
- nome legível do parâmetro: `self.context.controller.params["kp"].label`
- tipo do parâmetro: `self.context.controller.params["kp"].type`

## Básico de `compute(snapshot)`

O snapshot do controlador inclui:

- `cycle_id`
- `timestamp`
- `dt_s`
- `plant`
- `setpoints`
- `sensors`
- `actuators`
- `variables_by_id`
- `controller`

### O `snapshot` carrega os parâmetros do controlador?

Sim.

O snapshot inclui uma cópia serializada do controlador atual em:

- `snapshot["controller"]`

E isso inclui também:

- `snapshot["controller"]["params"]`

Exemplo:

- `snapshot["controller"]["params"]["kp"]["value"]`
- `snapshot["controller"]["params"]["kp"]["label"]`
- `snapshot["controller"]["params"]["kp"]["type"]`

Diferença prática:

- `self.context.controller.params["kp"].value` usa objeto com atributos
- `snapshot["controller"]["params"]["kp"]["value"]` usa dicionário serializado

Normalmente, para escrever o controlador, prefira:

- parâmetros e bindings: `self.context.controller`
- sinais do ciclo: `snapshot`

### Estrutura útil de `snapshot`

Campos mais usados:

- `snapshot["cycle_id"]`
- `snapshot["timestamp"]`
- `snapshot["dt_s"]`
- `snapshot["plant"]["id"]`
- `snapshot["plant"]["name"]`
- `snapshot["setpoints"]`
- `snapshot["sensors"]`
- `snapshot["actuators"]`
- `snapshot["variables_by_id"]`
- `snapshot["controller"]`

Leituras típicas:

- PV atual: `snapshot["sensors"].get(sensor_id, 0.0)`
- SP atual: `snapshot["setpoints"].get(sensor_id, 0.0)`
- readback de atuador: `snapshot["actuators"].get(actuator_id, 0.0)`
- unidade da variável: `snapshot["variables_by_id"][sensor_id]["unit"]`
- setpoint público cadastrado da variável: `snapshot["variables_by_id"][sensor_id]["setpoint"]`

Exemplo completo:

```python
def compute(self, snapshot: Dict[str, Any]) -> Dict[str, float]:
    sensor_id = self.context.controller.input_variable_ids[0]
    actuator_id = self.context.controller.output_variable_ids[0]

    kp = self.context.controller.params["kp"].value
    pv = snapshot["sensors"].get(sensor_id, 0.0)
    sp = snapshot["setpoints"].get(sensor_id, 0.0)
    dt_s = snapshot["dt_s"]
    unit = snapshot["variables_by_id"][sensor_id]["unit"]

    self.context.logger.debug(
        "Calculando controlador",
        {"sensor_id": sensor_id, "pv": pv, "sp": sp, "dt_s": dt_s, "unit": unit},
    )

    erro = sp - pv
    return {actuator_id: kp * erro}
```

## Payload de retorno do Controlador

`compute()` deve retornar um mapa `{actuator_id: valor}`:

```json
{
  "actuator_1": 42.0
}
```

Regras práticas:

- use ids de atuador presentes em `output_variable_ids`
- valores devem ser numéricos finitos
- ids inválidos são ignorados
- tipos numéricos inválidos podem invalidar o ciclo daquele controlador

## Unidades Públicas vs Unidades do Dispositivo

As variáveis da planta definem as unidades e limites públicos. O driver é o lugar certo para converter para o protocolo do dispositivo.

Exemplo:

- faixa pública do atuador: `0..100`
- duty cycle do dispositivo: `0..255`
- `write()` converte saída pública para unidade crua
- `read()` converte feedback cru de volta para unidade pública

## Logs e Bibliotecas Nativas

A runtime reserva `stdout` para o protocolo interno em JSON.

Recomendação para autores de plugin:

- use logging Python ou `stderr` para logs
- evite imprimir texto arbitrário em `stdout`
- ao chamar bibliotecas nativas, prefira bibliotecas que loguem em `stderr`

O runner atual redireciona a maior parte da saída nativa comum de `stdout` para `stderr`, mas log explícito em `stderr` continua sendo o caminho mais seguro para diagnóstico de plugin.
