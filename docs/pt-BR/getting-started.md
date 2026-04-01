# Primeiros Passos

[![English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](../en/getting-started.md)
[![Português](https://img.shields.io/badge/Idioma-Portugu%C3%AAs-16a34a?style=for-the-badge)](getting-started.md)

## 1. Abra a Aplicação

Se você executa o Senamby a partir do código-fonte, a aplicação desktop fica em `apps/desktop`.

Comandos típicos:

- `pnpm --dir apps/desktop install`
- `pnpm --dir apps/desktop tauri dev`

Se você usa um build empacotado, basta abrir o Senamby normalmente no sistema operacional.

## 2. Entenda os Três Módulos Principais

Quando o app abre, a barra lateral organiza a experiência em três áreas:

- **Plotter**: plantas ao vivo, ações de runtime, gráficos, exportação e edição de controladores
- **Analyzer**: análise offline de arquivos JSON exportados
- **Plugins**: definições reutilizáveis de drivers e controladores

Se for seu primeiro uso, comece em `Plugins`, depois vá para `Plotter`, e deixe o `Analyzer` para depois da exportação.

## 3. Entenda o Workspace

O Senamby guarda seus arquivos em:

`Documents/Senamby/workspace`

Pastas importantes:

- `drivers/`: plugins persistidos de driver
- `controllers/`: plugins persistidos de controlador
- `plants/`: registries salvos das plantas
- `envs/`: ambientes Python reutilizados
- `runtimes/`: arquivos de bootstrap e assets compartilhados das sessões conectadas

Normalmente você não edita esses arquivos manualmente. A UI e o backend cuidam disso.

## 4. Crie ou Importe um Plugin de Driver

Antes de uma planta rodar, ela precisa de um driver.

Passo a passo:

1. Abra o módulo `Plugins`
2. Selecione a categoria `Driver`
3. Escolha um destes caminhos:
   - criar um plugin novo na interface
   - importar um arquivo JSON de plugin
   - reutilizar um plugin já carregado do workspace
4. Confirme que o plugin possui:
   - nome
   - runtime `python`
   - classe de entrada
   - arquivo-fonte, geralmente `main.py`
   - campos de schema para a configuração que a instância da planta vai preencher
5. Salve e confira se o plugin aparece no catálogo

## 5. Opcionalmente Crie Plugins de Controlador

Controladores são opcionais. Adicione-os quando a planta precisar calcular saídas de atuador com base nos dados lidos.

Passo a passo:

1. Continue no módulo `Plugins`
2. Troque para a categoria `Controller`
3. Crie ou importe um ou mais controladores
4. Garanta que cada controlador exponha os parâmetros e bindings esperados pela planta
5. Salve e confirme a presença deles no catálogo

## 6. Crie ou Importe uma Planta

Vá para o módulo `Plotter`.

Você pode:

- criar uma planta nova pela interface
- importar um arquivo JSON de planta com preview antes do cadastro

Ao criar uma planta, preencha estas partes com atenção:

1. **Identidade da planta**
   - nome
   - tempo de amostragem em milissegundos
2. **Variáveis**
   - sensores para valores medidos do processo
   - atuadores para saídas manipuladas
3. **Driver**
   - escolha o plugin de driver
   - preencha a configuração exigida pelo schema do plugin
4. **Controladores** (opcional)
   - adicione instâncias de controlador
   - faça os bindings de sensores e atuadores
   - ajuste parâmetros e estado de ativação

## 7. Conecte a Planta

Quando a planta estiver configurada:

1. abra a planta no módulo `Plotter`
2. clique para conectar
3. aguarde a runtime:
   - resolver o driver e os controladores ativos
   - preparar ou reutilizar o ambiente Python
   - iniciar o ciclo ao vivo `read -> control -> write -> publish`
4. confirme que a telemetria começou a aparecer nos gráficos

Se a planta não conectar, consulte [Solução de Problemas](troubleshooting.md).

## 8. Trabalhe com a Sessão ao Vivo

Com a planta conectada, você pode:

- acompanhar sensores e atuadores em tempo real
- ajustar setpoints de sensores
- editar parâmetros de controladores
- salvar mudanças de controlador e deixar o app fazer hot update quando possível
- pausar a plotagem temporariamente sem parar a runtime

Detalhe importante:

- `Pause` pausa só a plotagem na UI
- a runtime continua rodando em segundo plano
- ao retomar, a telemetria acumulada volta para os gráficos

## 9. Exporte e Analise os Dados

Na sessão do plotter, você pode exportar:

- CSV para tratamento tabular
- JSON para replay estruturado e uso no Analyzer

Fluxo recomendado:

1. rode a planta por tempo suficiente para coletar dados úteis
2. exporte JSON pela barra do plotter
3. abra o módulo `Analyzer`
4. carregue o arquivo JSON exportado
5. inspecione sensores, setpoints e atuadores vinculados em modo offline

## 10. Desconectar, Fechar ou Remover

Essas ações são diferentes:

- **Desconectar**: encerra a runtime ao vivo, mas mantém a planta aberta na sessão atual
- **Fechar planta**: descarrega a planta da sessão e encerra a runtime se necessário, mas preserva o arquivo salvo
- **Remover planta**: descarrega a planta e apaga o registry salvo do workspace

Regra importante de reabertura:

- plantas não são recarregadas automaticamente no startup
- uma planta fechada precisa ser aberta/importada novamente
- quando for reaberta, as instâncias de controlador começam inativas
