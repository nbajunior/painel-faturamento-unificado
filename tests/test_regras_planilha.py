# -*- coding: utf-8 -*-
"""Regras trazidas do painel de acompanhamento (planilha da área), unificadas neste projeto:
estrutura tarifária e valor mínimo sugerido, situação dos ciclos, conferência das economias, cancelamento,
economias "Outros", mínimo da categoria pública e ajustes de água/esgoto na conferência do Em Análise."""
import datetime as dt
import json
import os
import shutil
import subprocess

import pandas as pd
import pytest

from faturamento import Sessao, tarifas
from faturamento import situacao_ciclos as sc
from faturamento.comparativo import confere_economias_agua
from faturamento.config import REGRAS
from faturamento.leitura import chave_grupo
from faturamento.top20 import aplica_ajustes_top20

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOJE = dt.date(2026, 9, 20)

# (categoria, consumo m³, economias, valor de água esperado em R$) — conferidos à mão com a tabela tarifária
CASOS_TARIFA = [
    ("RESIDENCIAL", 22, 1, 15 * 6.5231 + 7 * 14.3508),       # passou do mínimo: 1ª faixa progressiva
    ("RESIDENCIAL", 15, 1, 15 * 5.6941),                     # no mínimo: tarifa normal
    ("RESIDENCIAL", 30, 2, 2 * 15 * 5.6941),                 # 15 m³ por economia
    ("Social Especial", 40, 2, 2 * 15 * 2.0083),             # não cobra acima do mínimo
    ("COMERCIAL", 35, 1, 20 * 22.1784 + 10 * 39.0731 + 5 * 41.7476),
    ("Pública", 45, 3, 3 * 15 * 8.6105),                     # mínimo da pública = 15
    ("INDUSTRIAL", 150, 1, 30 * 30.6584 + 100 * 35.2245 + 20 * 37.1814),
]


@pytest.fixture(scope="module")
def sessao_pequena(tmp_path_factory):
    from dados_sinteticos import gera_pasta
    destino = tmp_path_factory.mktemp("regras") / "dados"
    gera_pasta(str(destino), n_ligacoes=120, n_grupos=4)
    s = Sessao(str(destino), progresso=lambda pct, desc: None)
    s.ctx.data_hoje = HOJE
    s.top20 = s.preparar()
    s.continuar()
    return s


# ---------- estrutura tarifária ----------

def test_valor_de_agua_pela_tarifa():
    e = tarifas.padrao()
    for cat, consumo, eco, esperado in CASOS_TARIFA:
        assert tarifas.valor_agua(e, cat, consumo, eco) == pytest.approx(esperado), cat
    assert tarifas.valor_agua(e, "CATEGORIA SEM TARIFA", 10, 1) is None
    assert tarifas.valor_agua(e, "RESIDENCIAL", 10, 0) is None


def test_esgoto_e_100_por_cento_da_agua():
    e = tarifas.padrao()
    agua, esgoto = tarifas.valor_conta(e, "RESIDENCIAL", 22, 1, tem_esgoto=True)
    assert esgoto == pytest.approx(agua)
    assert tarifas.valor_conta(e, "RESIDENCIAL", 22, 1, tem_esgoto=False)[1] == 0


def test_site_calcula_igual_ao_python():
    """tarifas_site.js (conferência no navegador) e tarifas.py dão o mesmo valor nos mesmos casos."""
    if not shutil.which("node"):
        pytest.skip("node não instalado")
    e = tarifas.para_site(tarifas.padrao())
    casos = [[c, consumo, eco] for c, consumo, eco, _ in CASOS_TARIFA] + [["RESIDENCIAL", 0, 1], ["X", 5, 1]]
    js = ("const T=require(process.argv[1]); const [e,c]=JSON.parse(process.argv[2]);"
          "console.log(JSON.stringify(c.map(([cat,cons,eco])=>[T.valorAgua(e,cat,cons,eco),T.minimoM3(e,cat,eco)])))")
    saida = subprocess.run(["node", "-e", js, os.path.join(RAIZ, "tarifas_site.js"), json.dumps([e, casos])],
                           capture_output=True, text=True, check=True).stdout
    estrutura = tarifas.padrao()
    for (cat, consumo, eco), (v_js, m_js) in zip(casos, json.loads(saida)):
        v_py = tarifas.valor_agua(estrutura, cat, consumo, eco)
        assert (v_js is None) == (v_py is None) and (v_py is None or v_js == pytest.approx(v_py)), cat
        assert m_js == tarifas.minimo_m3(estrutura, cat, eco)


def test_planilha_tarifaria_ida_e_volta(tmp_path):
    caminho = tmp_path / tarifas.NOME_ARQUIVO
    tarifas.gera_planilha_modelo(str(caminho))
    estrutura, avisos = tarifas.le_planilha(str(caminho))
    assert estrutura == tarifas.padrao() and avisos == []


def test_planilha_tarifaria_da_pasta_e_usada(tmp_path):
    """Com a planilha na pasta, a conferência usa as tarifas dela (reajuste sem mexer no código)."""
    from dados_sinteticos import gera_pasta
    pasta = tmp_path / "dados"
    gera_pasta(str(pasta), n_ligacoes=60, n_grupos=2)
    e = tarifas.padrao()
    e["RESIDENCIAL"]["faixas"][0][1] = 10.0                   # reajuste da 1ª faixa (tarifa normal)
    tarifas.gera_planilha_modelo(str(pasta / tarifas.NOME_ARQUIVO), e)
    s = Sessao(str(pasta), progresso=lambda pct, desc: None)
    r = s.preparar()
    assert r["fonteTarifas"].endswith(tarifas.NOME_ARQUIVO)
    assert r["tarifas"]["RESIDENCIAL"]["faixas"][0][1] == 10.0
    assert tarifas.valor_agua(s.ctx.tarifas, "RESIDENCIAL", 15, 1) == pytest.approx(150.0)
    assert not any("Nenhuma planilha Estrutura_Tarifaria" in a for a in s.ctx.avisos_base)


def test_sem_planilha_usa_a_tarifa_embutida_e_avisa(sessao_pequena):
    assert sessao_pequena.ctx.tarifas == tarifas.padrao()
    assert any("Estrutura_Tarifaria.xlsx" in a for a in sessao_pequena.ctx.avisos_base)


def test_planilha_com_linha_invalida_avisa(tmp_path):
    caminho = tmp_path / "t.xlsx"
    pd.DataFrame([{tarifas.COL_CATEGORIA: "RESIDENCIAL", tarifas.COL_MINIMO: 15, tarifas.COL_ATE: 15, tarifas.COL_NORMAL: "abc",
                   tarifas.COL_PROG: 1, tarifas.COL_LIMITA: "Não"},
                  {tarifas.COL_CATEGORIA: "COMERCIAL", tarifas.COL_MINIMO: 20, tarifas.COL_ATE: None, tarifas.COL_NORMAL: "22,1784",
                   tarifas.COL_PROG: None, tarifas.COL_LIMITA: None}]).to_excel(caminho, index=False)
    estrutura, avisos = tarifas.le_planilha(str(caminho))
    assert list(estrutura) == ["COMERCIAL"] and estrutura["COMERCIAL"]["faixas"] == [[None, 22.1784, 22.1784]]
    assert any("RESIDENCIAL" in a for a in avisos)


# ---------- conferência do Em Análise (dados enviados ao site e ajustes) ----------

def test_conferencia_envia_agua_esgoto_tarifas_e_em_analise(sessao_pequena):
    r = sessao_pequena.top20
    assert r["tarifas"] and r["percentualEsgoto"] == 1.0 and r["limiteDestaque"] == 100_000
    for l in r["linhas"]:
        assert l["agua"] + l["esgoto"] == pytest.approx(l["valor"], abs=0.02)
        if l["esgoto"] != 0:
            assert l["tem_esgoto"]                             # tem linha de esgoto: a tarifa soma o esgoto
    assert all("analise_agua" in g and "analise_esgoto" in g for g in r["grupos"])
    # em análise = contas não liberadas; nos dados sintéticos nenhuma conta está LIBERADA
    assert sum(g["analise_agua"] for g in r["grupos"]) > 0


def test_ajuste_com_agua_e_esgoto_separados(pasta_pequena):
    s = Sessao(pasta_pequena, progresso=lambda pct, desc: None)
    s.preparar()
    from faturamento.top20 import _ref_atual_base
    b = s.ctx.base_final
    ref = _ref_atual_base(s.ctx)
    mes = b[b["Referencia de Leitura"] == ref]
    rub = mes["Rubrica"].astype(str).str.upper()
    com_os_dois = set(mes.loc[rub.str.contains("ESGOTO"), "N. Ligação"]) & set(mes.loc[rub.str.contains("AGUA"), "N. Ligação"])
    lig = sorted(com_os_dois)[0]
    aplica_ajustes_top20(s.ctx, [{"ligacao": lig, "consumo": 15, "valor": 300.0, "agua": 170.0, "esgoto": 130.0}])
    m = s.ctx.base_final[(s.ctx.base_final["N. Ligação"] == lig) & (s.ctx.base_final["Referencia de Leitura"] == ref)]
    r = m["Rubrica"].astype(str).str.upper()
    assert m.loc[r.str.contains("AGUA"), "Valor (R$)"].sum() == pytest.approx(170.0)
    assert m.loc[r.str.contains("ESGOTO"), "Valor (R$)"].sum() == pytest.approx(130.0)
    assert (m["Consumo Faturado"] == 15).all()


def test_data_de_hoje_vem_do_site(pasta_pequena):
    import executor_web
    executor_web.preparar(pasta_pequena, lambda pct, desc: None, "2026-09-20")
    assert executor_web._estado["sessao"].ctx.data_hoje == HOJE


# ---------- situação dos ciclos ----------

@pytest.mark.parametrize("data, tipos, esperado", [
    (HOJE, {"EM ANALISE"}, sc.LIS),                           # LIS vence: lido hoje, mesmo com contas em análise
    (HOJE, set(), sc.LIS),
    (dt.date(2026, 9, 5), {"LIBERADA"}, sc.LIBERADO),
    (dt.date(2026, 9, 5), {"LIBERADA", "EM ANALISE"}, sc.EM_ANALISE),
    (dt.date(2026, 9, 5), {"LIBERADA", "A REALIZAR LEITURA"}, sc.EM_ANALISE),   # base não atualizou
    (dt.date(2026, 9, 25), set(), sc.AGUARDANDO),            # leitura depois de hoje
    (None, set(), sc.AGUARDANDO),
    (dt.date(2026, 9, 25), {"LIBERADA"}, sc.LIBERADO),        # já tem contas: vale a situação das contas
    (dt.date(2026, 9, 5), set(), sc.EM_ANALISE),             # já lido e sem contas na base: em análise (com aviso)
])
def test_regra_da_situacao(data, tipos, esperado):
    assert sc.classifica(HOJE, data, tipos)[0] == esperado


def test_tipo_da_conta():
    assert [sc._tipo_conta(v) for v in ("Liberada", "LIBERADO", "Em Análise", "A REALIZAR LEITURA", "", None, "NORMAL")] == \
        ["LIBERADA", "LIBERADA", "EM ANALISE", "A REALIZAR LEITURA", "OUTRA", "OUTRA", "OUTRA"]


def test_situacao_dos_ciclos_na_base(sessao_pequena):
    ctx = sessao_pequena.ctx
    base = ctx.base_completa
    atual = base["Referencia de Leitura"] == ctx.ref_atual
    grupos = sorted(base.loc[atual, "Grupo"].map(chave_grupo).unique(), key=int)
    g_lib, g_ana, g_lis, g_real = grupos[:4]
    chave = base["Grupo"].map(chave_grupo)
    base.loc[atual, "Situacao Conta"] = "LIBERADA"
    primeira = base.index[atual & (chave == g_ana)][0]
    base.loc[primeira, "Situacao Conta"] = "EM ANALISE"
    base.loc[atual & (chave == g_real), "Situacao Conta"] = "A REALIZAR LEITURA"
    mes = ctx.ref_atual
    crono = pd.DataFrame({"Grupo": [g_lib, g_ana, g_lis, g_real, "99", "98"],
                          "Data da Leitura": ["05/09/2026", "06/09/2026", "20/09/2026", "07/09/2026", "25/09/2026", "08/09/2026"],
                          "Referencia Cronograma": [mes] * 6})
    ctx.cronograma, avisos_antes = crono, len(ctx.avisos_base)
    df = sc.calcula(ctx).set_index("Ciclo")
    assert df.loc[g_lib, "Situação"] == sc.LIBERADO and df.loc[g_lib, "Água Em análise"] == 0
    assert df.loc[g_ana, "Situação"] == sc.EM_ANALISE and df.loc[g_ana, "Contas em análise"] == 1
    assert df.loc[g_lis, "Situação"] == sc.LIS
    assert df.loc[g_real, "Situação"] == sc.EM_ANALISE
    assert df.loc["99", "Situação"] == sc.AGUARDANDO and df.loc["98", "Situação"] == sc.EM_ANALISE
    assert any("98" in a for a in ctx.avisos_base[avisos_antes:])     # lido e sem contas: avisa
    # valores: liberado + em análise = faturamento de água/esgoto do grupo
    sel = base[atual & (chave == g_ana)]
    serv = sel["Rubrica"].astype(str).str.upper()
    assert df.loc[g_ana, "Água Liberado"] + df.loc[g_ana, "Água Em análise"] == pytest.approx(
        sel.loc[serv.str.contains("AGUA"), "Valor (R$)"].sum())
    assert "Situação dos ciclos" in sc.gera_html(ctx)


# ---------- economias, cancelamento e mínimos ----------

def test_economias_fatura_e_consumo_conferem(sessao_pequena):
    r = sessao_pequena.ctx.resultados["conferencia_economias"]
    assert r["economias_fatura"] == r["economias_consumo"] and not r["so_no_consumo"] and not r["so_na_fatura"]


def test_economias_divergentes_geram_aviso(sessao_pequena):
    ctx = sessao_pequena.ctx
    original = ctx.consumo_economias
    try:
        extra = pd.DataFrame({"lig": ["999999"], "ref": [ctx.ref_atual], "eco": [3.0]})
        ctx.consumo_economias = pd.concat([original, extra], ignore_index=True)
        antes = len(ctx.avisos_base)
        r = confere_economias_agua(ctx)
        assert r["economias_consumo"] - r["economias_fatura"] == pytest.approx(3.0)
        assert r["so_no_consumo"] == ["999999"]
        assert "999999" in ctx.avisos_base[antes]
    finally:
        ctx.consumo_economias = original


def test_economias_outros_entram_no_total():
    assert "Qtd. Economia Outros" in REGRAS["colunas_economia_totais"]


def test_minimo_das_categorias_publicas_e_15():
    assert REGRAS["consumo_minimo_por_categoria"]["PUBLICA"] == 15
    assert REGRAS["consumo_minimo_por_categoria"]["PUB. ESTADUAL"] == 15


def test_rubricas_de_cancelamento_da_planilha():
    assert set(REGRAS["rubricas_cancelamento"]) == {"ABATIMENTO - M3", "CREDITO/DEBITO DE ARRECADACAO - VAN",
                                                    "DESCONTO JUDICIAL PROVISORIO", "DESCONTO", "CREDITO AJUSTE CONTA"}


def test_tabela_de_situacao_nao_usa_classe_de_outra_tabela(sessao_pequena):
    """O relatório recalcula ativas × cortadas pela primeira `table.tabela-ativa-cortada`: a situação dos ciclos
    (que vem antes, na aba Diretas) não pode usar essa classe."""
    html = sc.gera_html(sessao_pequena.ctx)
    assert "tabela-situacao-ciclos" in html and "tabela-ativa-cortada" not in html
