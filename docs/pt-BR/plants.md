# Plantas

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](../en/plants.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](plants.md)

## Criando uma Planta Passo a Passo

Ao criar uma planta no módulo `Plotter`, avance por estas partes em ordem.

### 1. Identidade da planta

Defina:

- nome da planta
- tempo de amostragem em milissegundos

### 2. Variáveis

Adicione as variáveis que representam o modelo público do processo.

Use:

- `sensor` para valores medidos
- `atuador` para valores de saída

Para cada variável, defina:

- nome de exibição
- unidade de engenharia
- setpoint padrão
- faixa pública mínima e máxima

Atuadores podem ser vinculados a um ou mais sensores para agrupamento na UI e bindings de controlador.

### 3. Instância de driver

Escolha o plugin de driver que a planta vai usar e preencha a configuração exigida pelo schema desse plugin.

### 4. Instâncias de controlador

Opcionalmente adicione um ou mais controladores e configure:

- nome de exibição do controlador
- estado ativo/inativo
- bindings de variáveis de entrada
- bindings de variáveis de saída
- valores de parâmetros

## Importando ou Abrindo uma Planta

O Senamby suporta abrir um arquivo JSON para preview antes da importação. Depois da importação:

- a planta é registrada no workspace
- dados e estatísticas importados podem ficar disponíveis para inspeção
- plugins referenciados são reconciliados com o workspace quando possível

Isso é útil quando:

- você recebeu um JSON de planta de outro ambiente
- quer inspecionar o arquivo antes de cadastrar
- precisa restaurar uma planta que não está carregada na sessão

## Estrutura Persistida de Planta

Na prática o registry pode ter mais detalhes, mas uma forma simplificada é:

```json
{
  "id": "plant_123",
  "name": "Forno 1",
  "sample_time_ms": 1000,
  "variables": [
    {
      "id": "var_0",
      "name": "Temperatura",
      "type": "sensor",
      "unit": "C",
      "setpoint": 50.0,
      "pv_min": 0.0,
      "pv_max": 100.0
    },
    {
      "id": "var_1",
      "name": "Heater 1",
      "type": "atuador",
      "unit": "%",
      "setpoint": 0.0,
      "pv_min": 0.0,
      "pv_max": 100.0
    }
  ],
  "driver": {
    "plugin_id": "plugin_driver",
    "config": {
      "port": "/dev/ttyACM0"
    }
  },
  "controllers": []
}
```

## Conectando uma Planta

Conectar uma planta inicia a runtime e a telemetria ao vivo.

Durante a conexão, o Senamby:

- valida o driver e os controladores ativos
- resolve os arquivos de plugin no workspace
- prepara ou reutiliza o ambiente Python
- envia o bootstrap para o runner Python

O que você deve esperar depois de uma conexão bem-sucedida:

- os gráficos começam a receber dados em tempo real
- o estado de runtime passa para conectado/rodando
- setpoints de sensores podem ser enviados ao vivo
- edições em controladores podem fazer hot update ou virar `pending_restart`

## Desconectando uma Planta

Desconectar:

- encerra a runtime ao vivo
- mantém a planta aberta na sessão atual
- preserva o arquivo salvo da planta

Use essa ação quando quiser parar a execução sem descarregar a interface da planta.

## Pausar e Retomar

Pausar e retomar são ações visuais de sessão. A runtime continua coletando e controlando em segundo plano enquanto a UI acumula backlog. Ao retomar, a telemetria acumulada é plotada.

Use pause quando:

- quiser inspecionar um gráfico congelado
- não quiser que a tela continue andando temporariamente
- ainda quiser manter a runtime rodando em segundo plano

## Fechando uma Planta

Fechar uma planta:

- encerra a runtime, se ela estiver conectada
- descarrega a planta da sessão atual
- preserva o arquivo persistido da planta

Regra importante de reabertura:

- quando a planta for reaberta, as instâncias de controlador começam inativas

## Removendo uma Planta

Remover uma planta:

- encerra a runtime, se necessário
- descarrega a planta da sessão
- apaga o registry persistido no workspace

## Setpoints

Setpoints são persistidos no registry da planta e, quando a planta está conectada, também enviados para a runtime em execução.

Na prática:

- sensores são as variáveis que normalmente possuem setpoints
- setpoint de atuador não é o caminho comum de controle ao vivo
- alterar o setpoint de um sensor atualiza o estado salvo e o estado da runtime quando conectada

## Exportando Dados da Planta

O plotter pode exportar a sessão coletada como:

- CSV
- JSON

Use CSV quando quiser planilhas ou scripts.

Use JSON quando quiser:

- arquivar a sessão de forma estruturada
- analisar offline no `Analyzer`
- preservar relações entre sensores, setpoints e atuadores
