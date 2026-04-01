# Drivers e Controladores

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](../en/drivers-and-controllers.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](drivers-and-controllers.md)

## Plugins de Driver

Drivers conectam o Senamby ao dispositivo real ou simulador. Um driver normalmente:

- lê sensores
- opcionalmente lê feedback dos atuadores
- escreve saídas de atuador quando há controladores ativos

A configuração do driver vem do schema do plugin e é salva na instância de driver da planta.

## Passo a Passo: Criando um Plugin de Driver

1. Abra o módulo `Plugins`
2. Escolha a categoria `Driver`
3. Crie ou importe um plugin
4. Defina:
   - nome do plugin
   - classe Python de entrada
   - arquivo-fonte, normalmente `main.py`
   - campos de schema necessários para configurar a instância do driver
   - dependências Python opcionais
5. Salve o plugin
6. No módulo `Plotter`, associe esse plugin a uma planta e preencha sua configuração

Responsabilidades típicas do driver:

- abrir e fechar a conexão externa
- ler dados de sensores
- opcionalmente ler feedback de atuadores
- converter unidades cruas do dispositivo para as unidades públicas da planta
- escrever saídas de atuador quando houver controladores ativos

## Plugins de Controlador

Controladores calculam saídas de atuador a partir do snapshot do ciclo atual. Uma instância de controlador guarda:

- identidade e nome de exibição
- bindings de entrada
- bindings de saída
- valores de parâmetros
- status de runtime

## Passo a Passo: Criando um Plugin de Controlador

1. Abra o módulo `Plugins`
2. Escolha a categoria `Controller`
3. Crie ou importe um plugin de controlador
4. Defina:
   - nome do plugin
   - classe Python de entrada
   - arquivo-fonte
   - schema de parâmetros do controlador
5. Salve o plugin
6. No módulo `Plotter`, adicione uma instância desse controlador à planta
7. Faça os bindings de:
   - sensores que o controlador lê
   - atuadores que o controlador escreve
8. Ajuste os valores iniciais dos parâmetros e o estado de ativação

Responsabilidades típicas do controlador:

- ler o snapshot atual
- comparar sensores e setpoints
- produzir saídas de atuador nas unidades públicas de engenharia da planta

## Atualizações em Runtime

Enquanto a planta está conectada, controladores podem ser adicionados ou editados em tempo real.

- se o ambiente Python atual conseguir carregar o conjunto atualizado, a runtime faz hot swap
- se a mudança exigir reconstrução do ambiente, o controlador fica como `pending_restart`

Exemplos de mudanças que ainda podem exigir reconexão:

- alterações de dependências
- mudanças de código-fonte que pedem rebuild do ambiente
- conjunto de plugins que deixa de ser compatível com a runtime atual

## Status de Runtime

Status atuais de controlador:

- `synced`: a configuração já está aplicada na runtime
- `pending_restart`: a configuração foi salva, mas a runtime precisa ser reconectada

## Regras de Remoção e Ativação

- um controlador ativo e sincronizado não pode ser removido enquanto estiver rodando
- desative primeiro, salve a mudança e só então remova
- se o controlador estiver inativo, a remoção costuma ser mais permissiva

## Regra de Unidade Pública

Controladores e plantas devem trabalhar nas unidades públicas da planta. Conversões cruas de dispositivo pertencem ao driver.

Exemplo:

- faixa pública do atuador: `0..100`
- duty cycle do Arduino: `0..255`
- saída do controlador: `0..100`
- conversão de escrita no driver: `0..100 -> 0..255`
- conversão de leitura no driver: `0..255 -> 0..100`

## Resumo do Contexto de Runtime

Em runtime:

- drivers recebem `context.config` e `context.plant`
- controladores recebem `context.controller` e `context.plant`
- controladores não recebem objetos internos de backend/runtime
- parâmetros do controlador chegam como objetos com campos como `.type`, `.value` e `.label`
