/* Estrutura tarifária no site (conferência do "Em Análise").
 * Mesmo cálculo de faturamento/tarifas.py — os testes (tests/test_tarifas.py) rodam os dois com os mesmos casos.
 * `estrutura`: {chave: {categoria, minimo, limita, faixas: [[até m³ | null, normal, progressiva], ...]}} (vem do Python).
 */
(function (raiz) {
  "use strict";
  // mesma chave de config.chave_texto: sem acento, só letras e números, maiúsculas ("Peq. Comércio" → "PEQCOMERCIO")
  function chave(texto) {
    return String(texto == null ? "" : texto).normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  }

  function valorAgua(estrutura, categoria, consumo, economias) {
    const e = estrutura && estrutura[chave(categoria)];
    if (!e || !economias || economias <= 0) return null;
    let porEco = Math.max(Number(consumo) || 0, 0) / economias;
    if (e.limita) porEco = Math.min(porEco, e.minimo);
    const progressiva = porEco > e.minimo;
    let total = 0, inicio = 0;
    for (const [ate, normal, prog] of e.faixas) {
      const fim = ate == null ? Infinity : ate;
      const usado = Math.max(0, Math.min(porEco, fim) - inicio);
      total += usado * (progressiva ? prog : normal);
      inicio = fim;
      if (porEco <= fim) break;
    }
    return total * economias;
  }

  function minimoM3(estrutura, categoria, economias) {
    const e = estrutura && estrutura[chave(categoria)];
    return !e || !economias || economias <= 0 ? null : e.minimo * economias;
  }

  /** {agua, esgoto} da conta (esgoto = percentual da água, só se a conta tem esgoto); null se não der para calcular. */
  function valorConta(estrutura, categoria, consumo, economias, temEsgoto, percentualEsgoto) {
    const agua = valorAgua(estrutura, categoria, consumo, economias);
    if (agua == null) return null;
    return { agua, esgoto: temEsgoto ? agua * (percentualEsgoto == null ? 1 : percentualEsgoto) : 0 };
  }

  const api = { chave, valorAgua, minimoM3, valorConta };
  if (typeof module !== "undefined" && module.exports) module.exports = api;   // testes (node)
  raiz.Tarifas = api;
})(typeof window !== "undefined" ? window : globalThis);
