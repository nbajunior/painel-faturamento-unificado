# -*- coding: utf-8 -*-
"""Estrutura tarifária de água (valor de uma conta a partir do consumo) e a planilha Estrutura_Tarifaria.xlsx.

Usada na conferência do "Em Análise": ao digitar o consumo de uma conta, o site recalcula o valor pela tarifa, e a
coluna "valor mínimo sugerido" aplica a tarifa ao consumo mínimo da categoria. O site (index.html) repete o mesmo
cálculo em JavaScript; os testes conferem as duas versões com os mesmos casos.

Regras (as mesmas do painel anterior, validadas contra contas reais):
  - O consumo da matrícula é dividido igualmente pelas economias; cada economia é cobrada como uma conta.
  - Faixas cumulativas: cada faixa cobra só os m³ que caem dentro dela.
  - Se o consumo por economia passa do mínimo da categoria, todas as faixas usam a tarifa progressiva (na prática só a
    1ª faixa da Residencial tem valor progressivo diferente do normal).
  - "Limita ao mínimo" (Social Especial): o consumo acima do mínimo não é cobrado.
  - Esgoto = percentual da água (regras.json → percentual_esgoto_sobre_agua; hoje 100%).

A planilha tem uma linha por faixa:
  Categoria | Minimo (m3 por economia) | Faixa ate (m3) | Tarifa Normal (R$/m3) | Tarifa Progressiva (R$/m3) | Limita ao minimo
"Faixa ate" vazio = última faixa (sem limite).
"""
import pandas as pd

from .config import REGRAS, chave_texto

NOME_ARQUIVO = "Estrutura_Tarifaria.xlsx"
COL_CATEGORIA = "Categoria"
COL_MINIMO = "Minimo (m3 por economia)"
COL_ATE = "Faixa ate (m3)"
COL_NORMAL = "Tarifa Normal (R$/m3)"
COL_PROG = "Tarifa Progressiva (R$/m3)"
COL_LIMITA = "Limita ao minimo"
COLUNAS = [COL_CATEGORIA, COL_MINIMO, COL_ATE, COL_NORMAL, COL_PROG, COL_LIMITA]
# o que identifica o arquivo na pasta (comparado sem acento/pontuação, ver config.chave_texto)
CHAVES_IDENTIFICACAO = {chave_texto(c) for c in (COL_CATEGORIA, COL_ATE, COL_NORMAL, COL_PROG)}

PERCENTUAL_ESGOTO = float(REGRAS.get("percentual_esgoto_sobre_agua", 1.0))


def padrao():
    """Estrutura embutida em regras.json (usada quando a pasta não tem a planilha)."""
    return {chave_texto(c): {"categoria": c, "minimo": float(v["minimo"]), "limita_ao_minimo": bool(v.get("limita_ao_minimo")),
                             "faixas": [[None if a is None else float(a), float(n), float(p)] for a, n, p in v["faixas"]]}
            for c, v in REGRAS["estrutura_tarifaria_padrao"].items()}


def eh_planilha_tarifa(colunas):
    return CHAVES_IDENTIFICACAO.issubset({chave_texto(c) for c in colunas})


def _num(v):
    if v is None or (isinstance(v, float) and v != v) or str(v).strip() == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return float(t)


def le_planilha(caminho, aba=0):
    """Lê a planilha. Devolve (estrutura, avisos). Categoria com faixa inválida fica de fora, com aviso."""
    df = pd.read_excel(caminho, sheet_name=aba, dtype=object)
    nomes = {chave_texto(c): c for c in df.columns}
    col = {k: nomes.get(chave_texto(k)) for k in COLUNAS}
    avisos, estrutura = [], {}
    for _, r in df.iterrows():
        cat = r.get(col[COL_CATEGORIA])
        if cat is None or (isinstance(cat, float) and cat != cat) or not str(cat).strip():
            continue
        k = chave_texto(cat)
        try:
            ate, normal = _num(r.get(col[COL_ATE])), _num(r.get(col[COL_NORMAL]))
            prog = _num(r.get(col[COL_PROG])) if col[COL_PROG] else None
            minimo = _num(r.get(col[COL_MINIMO])) if col[COL_MINIMO] else None
        except ValueError:
            avisos.append(f"Estrutura tarifária: linha de {cat} com número inválido (ignorada).")
            continue
        if normal is None:
            avisos.append(f"Estrutura tarifária: linha de {cat} sem tarifa normal (ignorada).")
            continue
        limita = str(r.get(col[COL_LIMITA]) if col[COL_LIMITA] else "").strip().upper() in ("SIM", "S", "X", "1", "TRUE", "VERDADEIRO")
        e = estrutura.setdefault(k, {"categoria": str(cat).strip(), "minimo": None, "limita_ao_minimo": False, "faixas": []})
        if minimo is not None:
            e["minimo"] = minimo
        e["limita_ao_minimo"] = e["limita_ao_minimo"] or limita
        e["faixas"].append([ate, normal, normal if prog is None else prog])
    for k, e in list(estrutura.items()):
        e["faixas"].sort(key=lambda f: float("inf") if f[0] is None else f[0])
        if e["minimo"] is None:
            avisos.append(f"Estrutura tarifária: {e['categoria']} sem consumo mínimo (categoria ignorada).")
            del estrutura[k]
        elif e["faixas"][-1][0] is not None:
            e["faixas"].append([None] + e["faixas"][-1][1:])          # sem faixa aberta: a última vale acima também
    return estrutura, avisos


def valor_agua(estrutura, categoria, consumo, economias):
    """Valor de água (R$) da matrícula; None se a categoria não estiver na estrutura ou sem economias."""
    e = estrutura.get(chave_texto(categoria))
    if not e or not economias or economias <= 0:
        return None
    por_eco = max(float(consumo or 0), 0.0) / economias
    if e["limita_ao_minimo"]:
        por_eco = min(por_eco, e["minimo"])
    progressiva = por_eco > e["minimo"]
    total, inicio = 0.0, 0.0
    for ate, normal, prog in e["faixas"]:
        fim = float("inf") if ate is None else ate
        usado = max(0.0, min(por_eco, fim) - inicio)
        total += usado * (prog if progressiva else normal)
        inicio = fim
        if por_eco <= fim:
            break
    return total * economias


def minimo_m3(estrutura, categoria, economias):
    e = estrutura.get(chave_texto(categoria))
    return None if not e or not economias or economias <= 0 else e["minimo"] * economias


def valor_conta(estrutura, categoria, consumo, economias, tem_esgoto):
    """(água, esgoto) da matrícula; (None, None) se não der para calcular."""
    a = valor_agua(estrutura, categoria, consumo, economias)
    if a is None:
        return None, None
    return a, (a * PERCENTUAL_ESGOTO if tem_esgoto else 0.0)


def para_site(estrutura):
    """Formato enviado ao site (JSON): {chave: {categoria, minimo, limita, faixas}}."""
    return {k: {"categoria": e["categoria"], "minimo": e["minimo"], "limita": e["limita_ao_minimo"], "faixas": e["faixas"]}
            for k, e in estrutura.items()}


def gera_planilha_modelo(caminho, estrutura=None):
    """Grava a planilha no formato esperado (com a estrutura embutida, se nenhuma for passada)."""
    estrutura = estrutura or padrao()
    linhas = []
    for e in estrutura.values():
        for i, (ate, normal, prog) in enumerate(e["faixas"]):
            linhas.append({COL_CATEGORIA: e["categoria"], COL_MINIMO: e["minimo"] if i == 0 else None, COL_ATE: ate,
                           COL_NORMAL: normal, COL_PROG: prog, COL_LIMITA: ("Sim" if e["limita_ao_minimo"] else "Não") if i == 0 else None})
    pd.DataFrame(linhas, columns=COLUNAS).to_excel(caminho, index=False, sheet_name="Tarifas")
