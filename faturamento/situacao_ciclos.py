# -*- coding: utf-8 -*-
"""Aba Diretas — situação de cada ciclo (grupo de leitura) no mês atual, como na planilha de acompanhamento.

Situação (na ordem de prioridade, quando o ciclo se encaixa em mais de uma):
  1. LIS          — hoje é o dia de leitura do ciclo pelo cronograma (não importa o que já esteja na base).
  2. Em análise   — ao menos uma conta do ciclo com Situação Conta = EM ANALISE; ou A REALIZAR LEITURA (fora do dia de
                    leitura: a base não atualizou); ou situação vazia/desconhecida (com aviso).
  3. Liberado     — todas as contas do ciclo com Situação Conta = LIBERADA.
  4. Aguardando   — ciclo sem contas na base, com leitura depois de hoje pelo cronograma (ou sem data no cronograma).
Ciclo sem contas na base e com a leitura já passada pelo cronograma aparece como Em análise, com aviso (a base não trouxe
as contas de um ciclo que já foi lido).
"Hoje" é a data do computador de quem roda a análise (ver executor_web.preparar).
Valores: água e esgoto de cada ciclo separados em Liberado (contas LIBERADA) e Em análise (as demais).
"""
import datetime as dt
import html

import pandas as pd

from .formatacao import normaliza_texto

LIS, EM_ANALISE, LIBERADO, AGUARDANDO = "LIS", "Em análise", "Liberado", "Aguardando"
CORES = {LIS: ("#E8F0FB", "#1F5A96"), EM_ANALISE: ("#FFF1E6", "#B4520A"), LIBERADO: ("#E7F5EC", "#1E7A45"),
         AGUARDANDO: ("#EEF0F3", "#5B6573")}
LIMITE_DESTAQUE = 100_000          # R$ de água em análise no ciclo: destaque em vermelho (mesma régua da conferência)


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
    """Situação de um ciclo. `tipos_contas`: conjunto de tipos (_tipo_conta) das contas do ciclo na base (vazio = sem contas).
    Devolve (situação, motivo do aviso ou "")."""
    if data_leitura is not None and data_leitura == hoje:
        return LIS, ""
    if tipos_contas:
        if tipos_contas == {"LIBERADA"}:
            return LIBERADO, ""
        motivo = "situação de conta vazia ou desconhecida" if "OUTRA" in tipos_contas else ""
        return EM_ANALISE, motivo
    if data_leitura is None or data_leitura > hoje:
        return AGUARDANDO, ""
    return EM_ANALISE, "leitura já passou pelo cronograma, mas a base não trouxe contas do ciclo"


def calcula(ctx):
    """DataFrame com uma linha por ciclo do mês atual (grupos da fatura + grupos do cronograma no mês)."""
    from .comparativo import _sup_dos_grupos
    from .leitura import chave_grupo
    from .previsao import data_hoje
    hoje = data_hoje(ctx)
    ref = ctx.ref_atual
    base = ctx.base_completa if ctx.base_completa is not None else ctx.base_final
    atual = base[base["Referencia de Leitura"] == ref]
    col = _coluna_situacao(atual)
    serv = atual["__serv"] if "__serv" in atual.columns else atual["Rubrica"].astype(str).str.upper().map(
        lambda r: "E" if "ESGOTO" in r else "A" if "AGUA" in r else "")
    t = pd.DataFrame({"g": atual["Grupo"].map(chave_grupo).values, "s": serv.values,
                      "v": pd.to_numeric(atual["Valor (R$)"], errors="coerce").fillna(0).values,
                      "lig": atual["N. Ligação"].astype(str).values,
                      "tipo": (atual[col].map(_tipo_conta) if col else pd.Series("OUTRA", index=atual.index)).values})
    t = t[t["s"].isin(["A", "E"])]
    lib = t["tipo"] == "LIBERADA"

    datas = {}
    crono = getattr(ctx, "cronograma", None)
    if crono is not None and len(crono):
        c = crono[crono["Referencia Cronograma"] == ref]
        for g, d in zip(c["Grupo"].map(chave_grupo), c["Data da Leitura"]):
            d = _data(d)
            if d is not None:
                datas[g] = d                                  # a última linha do grupo no mês vale
        for g, d in zip(crono["Grupo"].map(chave_grupo), crono["Data da Leitura"]):
            if _data(d) == hoje:                              # lido hoje, mesmo se o cronograma do mês vier em outra aba
                datas[g] = hoje

    sup_grupo = _sup_dos_grupos(ctx, base)
    grupos = sorted(set(t["g"]) | set(datas), key=lambda g: (0, int(g)) if str(g).isdigit() else (1, str(g)))
    linhas, avisos = [], []
    for g in grupos:
        tg = t[t["g"] == g]
        sit, motivo = classifica(hoje, datas.get(g), set(tg["tipo"]))
        if motivo:
            avisos.append(f"{g}: {motivo}")
        soma = lambda serv, liberada: float(tg.loc[(tg["s"] == serv) & (lib[tg.index] if liberada else ~lib[tg.index]), "v"].sum())
        linhas.append({"Ciclo": g, "SUP": sup_grupo.get(g, "SEM SUP"), "Data da Leitura": datas.get(g), "Situação": sit,
                       "Água Liberado": soma("A", True), "Água Em análise": soma("A", False),
                       "Esgoto Liberado": soma("E", True), "Esgoto Em análise": soma("E", False),
                       "Contas em análise": int(tg.loc[~lib[tg.index], "lig"].nunique())})
    df = pd.DataFrame(linhas, columns=["Ciclo", "SUP", "Data da Leitura", "Situação", "Água Liberado", "Água Em análise",
                                       "Esgoto Liberado", "Esgoto Em análise", "Contas em análise"])
    if avisos:
        ctx.avisos_base.append("Situação dos ciclos — conferir: " + "; ".join(avisos) + ".")
    ctx.resultados["situacao_ciclos"] = df
    return df


def gera_html(ctx):
    """Card da aba Diretas com a situação de cada ciclo."""
    if getattr(ctx, "ref_atual", "") == "" or ctx.base_final is None:
        return ""
    from .previsao import data_hoje
    df = calcula(ctx)
    if not len(df):
        return ""
    fmt = lambda v: f"{v:,.0f}".replace(",", ".")
    e = html.escape
    corpo = ""
    for _, r in df.iterrows():
        fundo, cor = CORES[r["Situação"]]
        alerta = r["Água Em análise"] > LIMITE_DESTAQUE
        estilo_alerta = ' style="color:#B42318;font-weight:700;"' if alerta else ""
        data = r["Data da Leitura"].strftime("%d/%m") if r["Data da Leitura"] else "—"
        corpo += (f'<tr data-ciclo="{e(str(r["Ciclo"]))}" data-sit="{e(r["Situação"])}">'
                  f'<td style="text-align:center;">{e(str(r["Ciclo"]))}</td><td style="text-align:center;">{e(str(r["SUP"]))}</td>'
                  f'<td style="text-align:center;">{data}</td>'
                  f'<td style="text-align:center;"><span style="display:inline-block;padding:1px 10px;border-radius:10px;'
                  f'background:{fundo};color:{cor};font-weight:600;white-space:nowrap;">{e(r["Situação"])}</span></td>'
                  f'<td style="text-align:right;">{fmt(r["Água Liberado"])}</td>'
                  f'<td style="text-align:right;"{estilo_alerta}>{fmt(r["Água Em análise"])}</td>'
                  f'<td style="text-align:right;">{fmt(r["Esgoto Liberado"])}</td>'
                  f'<td style="text-align:right;">{fmt(r["Esgoto Em análise"])}</td>'
                  f'<td style="text-align:center;">{fmt(r["Contas em análise"])}</td></tr>')
    tot = {c: df[c].sum() for c in ("Água Liberado", "Água Em análise", "Esgoto Liberado", "Esgoto Em análise", "Contas em análise")}
    corpo += ('<tr class="linha-total"><td style="text-align:center;" colspan="4">Total</td>'
              + "".join(f'<td style="text-align:{"center" if c == "Contas em análise" else "right"};">{fmt(v)}</td>' for c, v in tot.items())
              + "</tr>")
    contagem = df["Situação"].value_counts()
    resumo = " · ".join(f"{s}: {int(contagem.get(s, 0))}" for s in (LIBERADO, EM_ANALISE, LIS, AGUARDANDO))
    return f"""
    <div class="card">
    <h2>Situação dos ciclos — {e(ctx.mes_atual)} (hoje: {data_hoje(ctx).strftime("%d/%m/%Y")})</h2>
    <p class="nota-secao"><b>Liberado</b>: todas as contas do ciclo liberadas. <b>Em análise</b>: ao menos uma conta em análise
    (ou a realizar leitura fora do dia de leitura). <b>LIS</b>: ciclo sendo lido hoje, pelo cronograma. <b>Aguardando</b>: leitura
    depois de hoje. Água em análise acima de R$ {fmt(LIMITE_DESTAQUE)} no ciclo em vermelho. {resumo}.</p>
    <table class="tabela-situacao-ciclos">
      <tr class="header-grupo"><th rowspan="2">Ciclo</th><th rowspan="2">SUP</th><th rowspan="2">Leitura</th><th rowspan="2">Situação</th>
          <th colspan="2">Água (R$)</th><th colspan="2">Esgoto (R$)</th><th rowspan="2">Contas em<br>análise</th></tr>
      <tr class="header-sub"><th>Liberado</th><th>Em análise</th><th>Liberado</th><th>Em análise</th></tr>
      {corpo}
    </table>
    </div>
    """
