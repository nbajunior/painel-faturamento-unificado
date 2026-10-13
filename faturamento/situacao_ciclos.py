# -*- coding: utf-8 -*-
"""Aba Diretas — situação de cada ciclo (grupo de leitura), como na planilha de acompanhamento.

Situação (na ordem de prioridade, quando o ciclo se encaixa em mais de uma) — a mesma regra da coluna "Situação" dos
comparativos (situacao_grupo.py), definida pela área:
  1. LIS          — hoje é o dia de leitura do ciclo pelo cronograma (não importa o que já esteja na base).
  2. Em Análise   — ao menos uma conta EM ANALISE (mesmo com contas A REALIZAR LEITURA); ou situação vazia/desconhecida
                    na fatura (com aviso).
  3. Aguardando   — ao menos uma conta A REALIZAR LEITURA (antes ou depois do dia de leitura); ou ciclo sem contas, com
                    leitura depois de hoje pelo cronograma (ou sem data no cronograma).
  4. Liberado     — todas as contas LIBERADA.
Ciclo sem contas na base e com a leitura já passada pelo cronograma aparece como Em Análise, com aviso.
A situação das contas vem da fatura de ciclo E do consumo (grupo já lido que ainda não chegou à fatura).
"Hoje" = dia seguinte à data de corte (D-1), a mesma referência do forecast; sem data de corte informada, é a data do
computador de quem roda a análise (ver executor_web.preparar).
O selo é editável no relatório (relatorio.js, sitEditar): a escolha manual vale para o grupo nos comparativos e aqui.

Ciclos considerados: só os que aparecem na fatura (em qualquer mês da pasta). O cronograma de leitura pode trazer grupos
de outras áreas da empresa: esses ficam de fora. No mês atual entram todos esses ciclos (inclusive os que ainda não
faturaram); num mês passado, os que faturaram naquele mês.

Filtros do relatório (relatorio.js): um bloco por superintendência × mês (classe sup-bloco, como DRE e Indiretas); o
orçado por ciclo tem uma coluna por planilha (data-src, filtro Comparar); as linhas têm data-grupo (filtro Grupo) e o
total é refeito no navegador (situacaoCiclosAtualiza).
Orçado do ciclo = peso do grupo no faturamento de água (ou esgoto) × orçado do mês — o mesmo das tabelas de orçado por
ciclo (orcado_ciclo.py).
"""
import datetime as dt
import html
import json

import pandas as pd

from .formatacao import normaliza_texto

LIS, EM_ANALISE, LIBERADO, AGUARDANDO = "LIS", "Em Análise", "Liberado", "Aguardando"     # os rótulos do selo editável
SITUACOES = (LIBERADO, EM_ANALISE, LIS, AGUARDANDO)
LIMITE_DESTAQUE = 100_000          # R$ de água em análise no ciclo: destaque em vermelho (mesma régua da conferência)
VALORES = ("Água Liberado", "Água Em análise", "Esgoto Liberado", "Esgoto Em análise", "Contas em análise")


def _data(valor):
    """Data da Leitura do cronograma (texto em vários formatos ou data) → date; None se não reconhecer."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    if isinstance(valor, (dt.datetime, pd.Timestamp)):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    t = str(valor).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    d = pd.to_datetime(t, dayfirst=True, errors="coerce")
    return None if pd.isna(d) else d.date()


def _coluna_situacao(df):
    return next((c for c in df.columns if normaliza_texto(c).startswith("SITUACAO CONTA")), None)


def _tipo_conta(situacao):
    """LIBERADA | EM ANALISE | A REALIZAR LEITURA | OUTRA (vazia ou desconhecida)."""
    s = normaliza_texto("" if situacao is None or (isinstance(situacao, float) and situacao != situacao) else situacao)
    if s.startswith("LIBERAD"):
        return "LIBERADA"
    if s == "EM ANALISE":
        return "EM ANALISE"
    if s.startswith("A REALIZAR"):
        return "A REALIZAR LEITURA"
    return "OUTRA"


def classifica(hoje, data_leitura, tipos_contas):
    """Situação de um ciclo. `tipos_contas`: conjunto de tipos (_tipo_conta) das contas do ciclo (fatura e consumo; vazio =
    sem contas). Devolve (situação, motivo do aviso ou "")."""
    if data_leitura is not None and data_leitura == hoje:
        return LIS, ""
    if tipos_contas:
        if "EM ANALISE" in tipos_contas:
            return EM_ANALISE, ""
        if "OUTRA" in tipos_contas:
            return EM_ANALISE, "situação de conta vazia ou desconhecida"
        if "A REALIZAR LEITURA" in tipos_contas:
            return AGUARDANDO, ""
        return LIBERADO, ""
    if data_leitura is None or data_leitura > hoje:
        return AGUARDANDO, ""
    return EM_ANALISE, "leitura já passou pelo cronograma, mas a base não trouxe contas do ciclo"


def hoje_da_situacao(ctx):
    """Dia seguinte à data de corte (D-1): a mesma referência do forecast e da coluna Situação dos comparativos."""
    from .previsao import data_corte
    return data_corte(ctx) + dt.timedelta(days=1)


def tipos_por_grupo(ctx, ref):
    """{chave do grupo: tipos das contas no mês} — fatura (base, vazia = OUTRA) + consumo (só situações informadas)."""
    contas = _contas(ctx)
    m = contas[contas["ref"] == ref]
    tipos = {g: set(t) for g, t in m.groupby("g")["tipo"]}
    resumo = getattr(ctx, "situacao_conta_resumo", None)
    if resumo is not None and len(resumo) and "fonte" in resumo.columns:
        r = resumo[(resumo["fonte"] == "consumo") & (resumo["ref"] == ref)]
        for g, an, lib, realizar, outra in zip(r["g"], r["em_analise"], r["liberada"], r["a_realizar"], r["outra"]):
            t = tipos.setdefault(g, set())
            if an:
                t.add("EM ANALISE")
            if realizar:
                t.add("A REALIZAR LEITURA")
            if outra:
                t.add("OUTRA")
            if lib or not (an or realizar or outra):
                t.add("LIBERADA")
    return tipos


def _ordem(g):
    return (0, int(g)) if str(g).isdigit() else (1, str(g))


def _base(ctx):
    return ctx.base_completa if getattr(ctx, "base_completa", None) is not None else ctx.base_final


def _contas(ctx):
    """Linhas de água/esgoto da base (todos os meses), uma vez: grupo (rótulo e chave), mês, serviço, valor, ligação, tipo."""
    cache = ctx.__dict__.setdefault("_cache_sit_ciclos", {})
    base = _base(ctx)
    if id(base) not in cache:
        from .leitura import chave_grupo
        col = _coluna_situacao(base)
        serv = base["__serv"] if "__serv" in base.columns else base["Rubrica"].astype(str).str.upper().map(
            lambda r: "E" if "ESGOTO" in r else "A" if "AGUA" in r else "")
        rotulo = base["Grupo"].astype(str).str.strip()
        tipos = (base[col].map({v: _tipo_conta(v) for v in base[col].dropna().unique()}).fillna("OUTRA")
                 if col else pd.Series("OUTRA", index=base.index))
        t = pd.DataFrame({"rotulo": rotulo.values, "g": rotulo.map({r: chave_grupo(r) for r in rotulo.unique()}).values,
                          "ref": base["Referencia de Leitura"].values, "s": serv.values,
                          "v": pd.to_numeric(base["Valor (R$)"], errors="coerce").fillna(0).values,
                          "lig": base["N. Ligação"].astype(str).values, "tipo": tipos.values})
        cache.clear()
        cache[id(base)] = t[t["s"].isin(["A", "E"])]
    return cache[id(base)]


def _rotulos(contas):
    """{chave do grupo: rótulo como aparece na fatura e no filtro de grupos} (o mais frequente)."""
    return contas.groupby("g")["rotulo"].agg(lambda s: s.value_counts().index[0]).to_dict()


def _datas_do_mes(ctx, ref, hoje):
    """{chave do grupo: Data da Leitura no mês `ref`} pelo cronograma; quem é lido hoje fica com a data de hoje."""
    from .leitura import chave_grupo
    datas = {}
    crono = getattr(ctx, "cronograma", None)
    if crono is None or not len(crono):
        return datas
    c = crono[crono["Referencia Cronograma"] == ref]
    for g, d in zip(c["Grupo"].map(chave_grupo), c["Data da Leitura"]):
        d = _data(d)
        if d is not None:
            datas[g] = d                                  # a última linha do grupo no mês vale
    if ref == ctx.ref_atual:
        for g, d in zip(crono["Grupo"].map(chave_grupo), crono["Data da Leitura"]):
            if _data(d) == hoje:                          # lido hoje, mesmo se o cronograma do mês vier em outra aba
                datas[g] = hoje
    return datas


def _sup_por_grupo(ctx, rotulos):
    """{chave do grupo: SUP} — a mesma relação do filtro Superintendência do cabeçalho."""
    from .dre import grupos_da_sup
    por_rotulo = grupos_da_sup(ctx, list(rotulos.values()))
    return {g: por_rotulo.get(r, "SEM SUP") for g, r in rotulos.items()}


def calcula(ctx, ref=None, sup=None, registra=True):
    """DataFrame com uma linha por ciclo no mês `ref` (padrão: o atual) e superintendência `sup` (padrão: todas).
    registra=True (mês atual, todas as SUPs): guarda o resultado para a aba Dados e acrescenta os avisos."""
    from .dre import TODAS
    hoje = hoje_da_situacao(ctx)
    ref = ref or ctx.ref_atual
    sup = sup or TODAS
    contas = _contas(ctx)
    rotulos = _rotulos(contas)                            # todos os ciclos da fatura, em qualquer mês
    sup_grupo = _sup_por_grupo(ctx, rotulos)
    do_mes = contas[contas["ref"] == ref]
    datas = _datas_do_mes(ctx, ref, hoje)
    if ref == ctx.ref_atual:
        grupos = set(rotulos)                              # mês atual: também os que ainda não faturaram
    else:
        grupos = set(do_mes["g"])                          # mês passado: os que faturaram naquele mês
    if sup != TODAS:
        grupos = {g for g in grupos if sup_grupo.get(g, "SEM SUP") == sup}
    por_grupo = dict(tuple(do_mes.groupby("g")))
    tipos = tipos_por_grupo(ctx, ref)
    linhas, avisos = [], []
    for g in sorted(grupos, key=_ordem):
        tg = por_grupo.get(g, do_mes.iloc[0:0])
        sit, motivo = classifica(hoje, datas.get(g), tipos.get(g, set()))
        if motivo:
            avisos.append(f"{rotulos[g]}: {motivo}")
        lib = tg["tipo"] == "LIBERADA"
        soma = lambda s, liberada: float(tg.loc[(tg["s"] == s) & (lib if liberada else ~lib), "v"].sum())
        linhas.append({"Ciclo": rotulos[g], "SUP": sup_grupo.get(g, "SEM SUP"), "Data da Leitura": datas.get(g), "Situação": sit,
                       "Água Liberado": soma("A", True), "Água Em análise": soma("A", False),
                       "Esgoto Liberado": soma("E", True), "Esgoto Em análise": soma("E", False),
                       "Contas em análise": int(tg.loc[~lib, "lig"].nunique())})
    df = pd.DataFrame(linhas, columns=["Ciclo", "SUP", "Data da Leitura", "Situação"] + list(VALORES))
    if registra:
        if avisos:
            ctx.avisos_base.append("Situação dos ciclos — conferir: " + "; ".join(avisos) + ".")
        ctx.resultados["situacao_ciclos"] = df
    return df


def orcado_por_ciclo(ctx, ref):
    """{planilha: {rótulo do grupo: (orçado água, orçado esgoto)}} no mês `ref` (vazio sem planilhas de orçado)."""
    from .dre import TODAS, fontes_rf, fontes_sup, orcado
    from .orcado_ciclo import pesos_por_ciclo
    fontes = fontes_rf(ctx) + fontes_sup(ctx)
    if not fontes:
        return {}
    pesos_a = pesos_por_ciclo(ctx, "AGUA")["valor"]
    pesos_e = pesos_por_ciclo(ctx, "ESGOTO")["valor"]
    r = {}
    for f in fontes:
        orc = orcado(ctx, f, TODAS, ref) or {}
        a, e = orc.get("dA"), orc.get("dE")
        if a is None and e is None:
            continue
        grupos = set(pesos_a) | set(pesos_e)
        r[f] = {g: (None if a is None else pesos_a.get(g, 0.0) * a, None if e is None else pesos_e.get(g, 0.0) * e) for g in grupos}
    return r


def _fmt(v):
    return "—" if v is None else f"{v:,.0f}".replace(",", ".")


def _tabela_html(ctx, df, ref, orc):
    """Tabela de um bloco (SUP × mês). Células numéricas com data-v (o navegador refaz o total com os grupos marcados)."""
    from .formatacao import nome_mes
    from .tabelas_html import selo_situacao
    e = lambda v: html.escape(str(v), quote=True)
    fontes = list(orc)
    if not len(df):
        return f'<div class="card"><h2>Situação dos ciclos — {e(nome_mes(ref))}</h2><p class="nota-secao">Sem ciclos neste mês.</p></div>'
    corpo = ""
    for _, r in df.iterrows():
        g = r["Ciclo"]
        data = r["Data da Leitura"].strftime("%d/%m") if r["Data da Leitura"] else "—"
        def celula(v, extra="", alerta=False):
            estilo = ' style="text-align:right;color:#B42318;font-weight:700;"' if alerta else ' style="text-align:right;"'
            return f'<td data-v="{"" if v is None else round(float(v), 2)}"{extra}{estilo}>{_fmt(v)}</td>'
        orc_a = "".join(celula(orc[f].get(g, (0.0, 0.0))[0], f' data-src="{e(f)}" data-col="oa-{i}"') for i, f in enumerate(fontes))
        orc_e = "".join(celula(orc[f].get(g, (0.0, 0.0))[1], f' data-src="{e(f)}" data-col="oe-{i}"') for i, f in enumerate(fontes))
        corpo += (f'<tr data-grupo="{e(g)}" data-sit="{e(r["Situação"])}">'
                  f'<td style="text-align:center;">{e(g)}</td><td style="text-align:center;">{e(r["SUP"])}</td>'
                  f'<td style="text-align:center;">{data}</td>'
                  f'<td style="text-align:center;">{selo_situacao(r["Situação"], g, ref)}</td>'
                  + orc_a + celula(r["Água Liberado"], ' data-col="al"')
                  + celula(r["Água Em análise"], ' data-col="aa" data-alerta="1"', r["Água Em análise"] > LIMITE_DESTAQUE)
                  + orc_e + celula(r["Esgoto Liberado"], ' data-col="el"') + celula(r["Esgoto Em análise"], ' data-col="ea"')
                  + f'<td data-v="{int(r["Contas em análise"])}" data-col="ca" style="text-align:center;">{_fmt(r["Contas em análise"])}</td></tr>')
    # total (refeito no navegador com os grupos marcados)
    tot = lambda col, i=None: (sum((orc[fontes[i]].get(g, (0.0, 0.0))[0 if col == "oa" else 1] or 0.0) for g in df["Ciclo"])
                               if i is not None else float(df[col].sum()))
    rodape = ('<tr class="linha-total"><td style="text-align:center;" colspan="4">Total</td>'
              + "".join(f'<td data-tot="oa-{i}" data-src="{e(f)}" style="text-align:right;">{_fmt(tot("oa", i))}</td>' for i, f in enumerate(fontes))
              + f'<td data-tot="al" style="text-align:right;">{_fmt(tot("Água Liberado"))}</td>'
              + f'<td data-tot="aa" style="text-align:right;">{_fmt(tot("Água Em análise"))}</td>'
              + "".join(f'<td data-tot="oe-{i}" data-src="{e(f)}" style="text-align:right;">{_fmt(tot("oe", i))}</td>' for i, f in enumerate(fontes))
              + f'<td data-tot="el" style="text-align:right;">{_fmt(tot("Esgoto Liberado"))}</td>'
              + f'<td data-tot="ea" style="text-align:right;">{_fmt(tot("Esgoto Em análise"))}</td>'
              + f'<td data-tot="ca" style="text-align:center;">{_fmt(tot("Contas em análise"))}</td></tr>')
    th_orc = lambda grp: "".join(f'<th data-grp="{grp}" data-src="{e(f)}">Orçado<br><small>{e(f)}</small></th>' for f in fontes)
    n = len(fontes) + 2
    contagem = df["Situação"].value_counts()
    resumo = " · ".join(f'{s}: <b data-cont="{e(s)}">{int(contagem.get(s, 0))}</b>' for s in SITUACOES)
    hoje = hoje_da_situacao(ctx).strftime("%d/%m/%Y")
    referencia = f"hoje: {hoje}" if ref == ctx.ref_atual else "mês fechado"
    return f"""
    <div class="card">
    <h2>Situação dos ciclos — {e(nome_mes(ref))} ({referencia})</h2>
    <p class="nota-secao"><b>Liberado</b>: todas as contas do ciclo liberadas. <b>Em Análise</b>: ao menos uma conta em análise.
    <b>LIS</b>: ciclo sendo lido hoje, pelo cronograma. <b>Aguardando</b>: leitura depois de hoje, ou contas a realizar leitura.
    Situação das contas pela fatura e pelo consumo; clique no selo para alterar manualmente (vale também nos comparativos). Orçado do ciclo = orçado do mês × peso do grupo no faturamento (o mesmo das tabelas de orçado por ciclo); as
    planilhas mostradas seguem o filtro Comparar. Água em análise acima de R$ {_fmt(LIMITE_DESTAQUE)} em vermelho.
    <span class="sit-ciclos-resumo">{resumo}</span>.</p>
    <table class="tabela-situacao-ciclos">
      <tr class="header-grupo"><th rowspan="2">Ciclo</th><th rowspan="2">SUP</th><th rowspan="2">Leitura</th><th rowspan="2">Situação</th>
          <th colspan="{n}" data-grp-top="agua">Água (R$)</th><th colspan="{n}" data-grp-top="esgoto">Esgoto (R$)</th>
          <th rowspan="2">Contas em<br>análise</th></tr>
      <tr class="header-sub">{th_orc("agua")}<th data-grp="agua">Liberado</th><th data-grp="agua">Em análise</th>
          {th_orc("esgoto")}<th data-grp="esgoto">Liberado</th><th data-grp="esgoto">Em análise</th></tr>
      {corpo}
      {rodape}
    </table>
    </div>
    """


def gera_html(ctx):
    """Blocos da aba Diretas: um por superintendência × mês (os filtros do cabeçalho mostram o escolhido)."""
    if getattr(ctx, "ref_atual", "") == "" or ctx.base_final is None:
        return ""
    from .dre import TODAS, lista_meses, lista_sups
    calcula(ctx)                                           # mês atual, todas as SUPs: avisos e aba Dados
    refs_base = set(_contas(ctx)["ref"].dropna().unique())
    meses = [m for m in lista_meses(ctx) if m in refs_base or m == ctx.ref_atual]
    blocos = []
    for m in meses:
        orc = orcado_por_ciclo(ctx, m)
        for sup in lista_sups(ctx):
            df = calcula(ctx, m, sup, registra=False)
            blocos.append(f'<div class="sup-bloco sit-ciclos-bloco" data-sup="{html.escape(sup, quote=True)}" '
                          f'data-mes="{html.escape(m, quote=True)}" style="display:none;">{_tabela_html(ctx, df, m, orc)}</div>')
    return "".join(blocos)
