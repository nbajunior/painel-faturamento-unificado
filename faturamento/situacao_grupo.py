# -*- coding: utf-8 -*-
"""Situação de cada grupo de leitura no mês vigente (coluna "Situação" das tabelas da aba Diretas).

A regra é a mesma da tabela "Situação dos ciclos" (situacao_ciclos.classifica), definida pela área:
  - LIS: o grupo que está sendo lido hoje (Data da Leitura do cronograma = hoje).
  - Em Análise: ao menos uma matrícula com Situacao Conta = EM ANALISE; ou situação vazia/desconhecida na fatura.
  - Aguardando: ao menos uma matrícula A REALIZAR LEITURA; ou grupo sem linhas no mês, com leitura depois de hoje.
  - Liberado: todas as matrículas LIBERADA.
  Grupo já lido pelo cronograma e sem linhas no mês: Em Análise.
A situação das matrículas vem da fatura de ciclo e do consumo do mês (grupo lido que ainda não chegou à fatura).
"Hoje" é o dia seguinte à data de corte (D-1), a mesma referência do forecast.
"""
import pandas as pd

from .config import SITUACAO_CONTA_EM_ANALISE
from .formatacao import normaliza_texto
from .situacao_ciclos import AGUARDANDO, EM_ANALISE, LIBERADO, LIS  # noqa: F401  (rótulos usados pelas tabelas)

LIBERADA = "LIBERADA"
COLUNAS_RESUMO = ["g", "ref", "n", "em_analise", "liberada", "a_realizar", "outra", "fonte"]


def resumo_situacao_conta(df, col_grupo, col_ref, col_sit="Situacao Conta", fonte="fatura"):
    """Por grupo × mês: quantas linhas com situação informada, se alguma está EM ANALISE, se todas estão LIBERADA, se
    alguma está A REALIZAR LEITURA e se alguma tem outro valor. `fonte`: "fatura" ou "consumo"."""
    if df is None or not len(df) or col_sit not in df.columns or col_grupo not in df.columns or col_ref not in df.columns:
        return pd.DataFrame(columns=COLUNAS_RESUMO)
    from .leitura import chave_grupo
    sit = df[col_sit]
    unicos = sit.dropna().unique()
    norm = sit.map(dict(zip(unicos, (normaliza_texto(v) for v in unicos))))
    an = (norm == SITUACAO_CONTA_EM_ANALISE)
    lib = norm.fillna("").str.startswith("LIBERAD")
    realizar = norm.fillna("").str.startswith("A REALIZAR")
    d = pd.DataFrame({"g": df[col_grupo].map({g: chave_grupo(g) for g in df[col_grupo].dropna().unique()}).values,
                      "ref": df[col_ref].astype(str).values, "an": an.values, "lib": lib.values, "real": realizar.values,
                      "outra": (~(an | lib | realizar)).values, "tem": (norm.notna() & (norm != "")).values})
    d = d[d["tem"] & d["g"].notna()]
    if not len(d):
        return pd.DataFrame(columns=COLUNAS_RESUMO)
    r = d.groupby(["g", "ref"]).agg(n=("tem", "size"), em_analise=("an", "any"), liberada=("lib", "all"),
                                    a_realizar=("real", "any"), outra=("outra", "any")).reset_index()
    r["fonte"] = fonte
    return r


def situacao_dos_grupos(ctx):
    """{chave do grupo: situação} para o mês vigente (ref_atual). Guarda em ctx.situacao_grupo."""
    if getattr(ctx, "situacao_grupo", None) is not None:
        return ctx.situacao_grupo
    from .leitura import chave_grupo
    from .situacao_ciclos import _datas_do_mes, classifica, hoje_da_situacao, tipos_por_grupo
    hoje = hoje_da_situacao(ctx)
    ref = ctx.ref_atual
    datas = _datas_do_mes(ctx, ref, hoje)
    tipos = tipos_por_grupo(ctx, ref)
    grupos = set(datas) | set(tipos)
    fat = getattr(ctx, "fatura_total", None)
    if fat is not None and "Grupo" in fat.columns:
        grupos |= {chave_grupo(g) for g in fat["Grupo"].dropna().unique()}
    ctx.situacao_grupo = {g: classifica(hoje, datas.get(g), tipos.get(g, set()))[0] for g in grupos}
    return ctx.situacao_grupo


def situacao(ctx, grupo):
    from .leitura import chave_grupo
    return situacao_dos_grupos(ctx).get(chave_grupo(grupo), "")
