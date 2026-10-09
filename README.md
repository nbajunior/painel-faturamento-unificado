# Análise de Faturamento — Água e Esgoto

Pipeline em Python (pandas) que compara o faturamento de água e esgoto do mês atual com o mês anterior e gera:

- `Top100_Quedas_Consumo.xlsx`: ranking das maiores quedas de consumo (água e esgoto)
- `Relatorio_Comparativo.html`: relatório com KPIs, gráfico, insights e tabelas filtráveis

## Pelo site (sem instalar nada)

Abra https://raniere3000-tech.github.io/analise-faturamento-agua-esgoto/, clique em **Selecionar pasta e analisar** e escolha a pasta com os arquivos. As subpastas também são lidas: arquivos com o mesmo nome em pastas diferentes entram todos; cópias idênticas e linhas repetidas entre arquivos contam uma vez só. Depois de ler os arquivos, o site mostra **todos os clientes com Situação Conta = EM ANALISE** do mês atual (ordenados por valor): você pode alterar o consumo ou o valor total (água + esgoto) de cada um e clicar em **Aplicar alterações e gerar relatório** (ou **Pular**). A alteração vale só para essa análise e só para o mês atual; os arquivos da pasta não mudam, e o relatório avisa quando há valores ajustados. Quando a análise chega a 100%, o relatório abre sozinho em tela cheia, com botões para baixar o HTML e o Top 100 em Excel. No Chrome e no Edge, o botão **Atualizar** relê a mesma pasta depois que você coloca arquivos novos nela.

O processamento roda no navegador: o site executa este mesmo script Python com o [Pyodide](https://pyodide.org) (`analisador.worker.js` + `executor_web.py`). Os arquivos não são enviados para nenhum servidor. Na primeira vez, o navegador baixa o Python (cerca de 30 MB), que depois fica em cache.

## Abas DRE e Indiretas

Além do comparativo (aba **Diretas**), o relatório tem a aba **DRE** (Projeto/Linha × Orçado RF × Orçado SUP × Realizado, com Δ% e Δ R$) e a aba **Indiretas**, com filtros no cabeçalho do site, como no DRE_Unificado: **Superintendência** (Todas, LAGOS, LESTE, SEM SUP), **Referência** (RF + SUP, só RF, só RF SUP), **Mês** e **Grupo** (vale para Resumo e Diretas). A aba Indiretas traz orçado × realizado por classe, evolução mensal por classe (com gráfico) e quantidade/ticket médio. Na aba **Diretas**, as tabelas de orçado por ciclo são duas (Água e Esgoto), com um seletor próprio para escolher a planilha de orçado (qualquer RF ou o RF SUP). O forecast das diretas projeta cada grupo que falta por economias × volume por economia × tarifa (até 6 meses de histórico, média ponderada), corrigidos pela tendência dos grupos que já faturaram no mês, com faixa provável e backtest; para usar 6 meses, coloque na pasta os 6 arquivos de consumo e a fatura com os 6 meses. Durante a geração, o site mostra cada gráfico, tabela e KPI que está sendo criado. O botão **Executivo** gera um PDF com KPIs, gráfico de faturamento por grupo, forecast, orçado por ciclo (água e esgoto), comparativos mês a mês, indiretas (financeiro e eventos) e justificativas, copiando a tela como está: filtros, orçado escolhido e botões de ocultar valem. Ao lado da barra aparece o tempo estimado para terminar (usa o tempo da última execução neste navegador; na primeira vez, o ritmo da própria barra). A aba **Dados** (a última) explica, para cada tabela e gráfico de cada aba, o que mostra, as bases e colunas usadas, o cálculo e a montagem, com botões para baixar a tabela (Excel) e as bases (CSV) para validar; ela também explica cada cálculo, com a memória de cálculo do forecast: parâmetros (data de corte D-1, dias úteis, grupos que faltam), os três métodos com os números do mês e um Excel para conferir. Coloque na mesma pasta:

| Arquivo | Como é reconhecido | Usado para |
|---|---|---|
| Serviço avulso | nome com "avulso" (ou colunas Endereco Ligacao/Nome da Localidade) | Indiretas (rubrica → classe: CORTE, RELIGAÇÃO, LNA, LNE, SANÇÃO, OUTROS) |
| Fatura do ciclo | colunas Rubrica/Valor Parcela | Diretas e Cancelamento (rubricas de cancelamento) |
| RF (ex.: `RF01T26.xlsx`) | colunas Sup, Rubrica e um mês por coluna | Orçado RF |
| RF SUP | mesmo modelo, com "SUP" no nome | Orçado SUP |
| `Estrutura_Tarifaria.xlsx` (opcional) | colunas Categoria, Faixa ate (m3), Tarifa Normal (R$/m3), Tarifa Progressiva (R$/m3) | Valor da conta pela tarifa na conferência do Em Análise (sem a planilha, usa a tabela embutida em `regras.json`, com aviso) |

A relação rubrica → classe, as rubricas de cancelamento e cidade → SUP ficam em `faturamento/regras.json`. A SUP vem da cidade (`Nome da Localidade`) da fatura ou do serviço avulso.

## Estrutura do código

O script do Colab foi dividido no pacote `faturamento/` (leitura, base, comparativo, análises, tabelas/painel HTML, relatório, pipeline). As regras de negócio (consumo mínimo, textos padrão, alertas) ficam em `faturamento/regras.json`; CSS e JS do relatório ficam em `faturamento/assets/`. `acompanhamento_faturamento.py` é só a linha de comando: `python acompanhamento_faturamento.py --pasta DADOS --modo local`.

## Testes

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Os testes usam dados sintéticos e rodam também no GitHub Actions a cada push. Se criar um arquivo novo no pacote, inclua-o em `ARQUIVOS_PY` no `analisador.worker.js` (um teste confere).

## Como usar o script

Defina `MODO_ORIGEM` no início do script:

| Modo | Onde roda | O que faz |
|---|---|---|
| `"upload"` | Google Colab | Mostra um botão para escolher os arquivos do computador e baixa os relatórios no final |
| `"drive"` | Google Colab | Lê os arquivos de uma pasta do Google Drive (`PASTA_DRIVE`) |
| `"local"` | No seu PC | Abre a janela para selecionar a pasta; salva os relatórios nela |

Para rodar localmente:

```bash
pip install pandas numpy openpyxl tqdm
python acompanhamento_faturamento.py
```

## Regras da planilha de acompanhamento (unificação com o painel de faturamento)

Regras definidas pela área e validadas em `tests/test_regras_planilha.py`:

- **Cancelamento:** só as rubricas `ABATIMENTO - M3`, `CREDITO/DEBITO DE ARRECADACAO - VAN`, `DESCONTO JUDICIAL PROVISORIO`, `DESCONTO` e `CREDITO AJUSTE CONTA` (as mesmas marcadas no filtro da planilha). COFINS, CRÉDITO DE ARRECADAÇÃO, IR ESTADUAL, IR MUNICIPAL e DESCONTO - RECADASTRO ficam de fora do cancelamento; IR ESTADUAL/MUNICIPAL vindos do serviço avulso continuam em "Outros" nas Indiretas.
- **Economias:** a coluna "Qtd. Economia Outros" entra na soma das economias. Matrícula faturada = Consumo Faturado maior que 0.
- **Conferência das economias de água:** o relatório conta pela Fatura (linhas VALOR DE AGUA com consumo > 0). A cada análise, a mesma conta é refeita pelo arquivo de Consumo (todas as ligações com consumo > 0, com ou sem esgoto); se as duas divergirem, a aba Dados mostra a diferença e as ligações de cada lado.
- **Consumo mínimo:** 15 m³ por economia nas categorias PUBLICA e PUB. ESTADUAL.
- **Situação dos ciclos (aba Diretas):** LIS = dia de leitura pelo cronograma é hoje (data do computador); Em análise = ao menos uma conta EM ANALISE, ou A REALIZAR LEITURA fora do dia de leitura; Liberado = todas as contas LIBERADA; Aguardando = leitura depois de hoje. Nessa ordem de prioridade. Ciclo já lido sem contas na base aparece como Em análise, com aviso. Valores de água e esgoto separados em liberado e em análise.
- **Conferência do Em Análise:** filtro por categoria (só para escolher as contas; o quadro por grupo continua com o total), valor mínimo sugerido por conta (consumo mínimo da categoria × economias, valor pela estrutura tarifária), botão para aplicar o mínimo numa conta ou nas marcadas, e recálculo automático do valor pela tarifa sempre que o consumo é digitado (esgoto = 100% da água, quando a conta tem esgoto). O quadro por grupo mostra o valor em análise de água e de esgoto, com destaque acima de R$ 100.000 de água.

O cálculo da tarifa existe em Python (`faturamento/tarifas.py`) e no navegador (`tarifas_site.js`); um teste confere que os dois dão o mesmo resultado.

## Premissas

- Na conferência do Top 20, só entram contas com `Situacao Conta` = EM ANALISE (coluna do arquivo de fatura ou consumo)
- O nome do arquivo de consumo contém o mês (ex.: `09-2026`)
- O nº da ligação é o mesmo em todas as bases
- Só considera as rubricas `VALOR DE AGUA` e `VALOR DE ESGOTO`
- Uma linha por ligação por mês
- O cronograma é lido em qualquer aba (e com título acima do cabeçalho) que tenha as colunas Grupo, Data da Leitura e Qts. Dias, e é cruzado com a fatura por grupo e mês (mês da Data da Leitura); sem o mês, usa a última linha do grupo. Só valem os ciclos que existem na fatura/consumo
