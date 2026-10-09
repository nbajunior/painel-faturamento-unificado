# Regras do repositório

- **Toda atualização muda a versão do cabeçalho do site.** Em `index.html`, aumente `VERSAO_SITE`
  (ex.: `"v16-20261006"` → `"v17-AAAAMMDD"`, com a data do dia) e o texto do `<span id="versao">`
  para o mesmo número. A mensagem do commit começa com essa versão (ex.: `v17: ...`).
- Rode `python -m pytest tests -q` antes de enviar.
- Arquivo novo no pacote `faturamento/` precisa entrar em `ARQUIVOS_PY` no `analisador.worker.js`.
- `tarifas_site.js` (cálculo da tarifa no navegador) espelha `faturamento/tarifas.py`: mudou um, mude o outro
  (o teste `test_site_calcula_igual_ao_python` compara os dois). Ao alterá-lo, atualize o `?v=` da tag
  `<script src="tarifas_site.js?v=...">` no `index.html` junto com a versão do site.
- **Publicação autorizada:** o dono do repositório autorizou mesclar sempre. Depois de validar
  (testes passando), abra o PR da branch de trabalho para a `main` e mescle — a `main` é o que o
  GitHub Pages publica. Antes de mesclar, confira que o PR já contém o último commit enviado.
