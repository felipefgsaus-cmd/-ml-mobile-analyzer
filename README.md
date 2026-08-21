# ML Analyzer FINAL

Versão consolidada.

Fluxo de recuperação:
1. ID do catálogo presente no link;
2. secondary_key das avaliações;
3. /items/{id};
4. Multi-GET /items;
5. busca pública /sites/MLB/search;
6. página pública do Mercado Livre;
7. catálogo /products/{id};
8. ofertas /products/{id}/items.

Objetivo:
- título
- preço e preço original
- vendedor e reputação
- avaliações
- perguntas
- descrição
- fotos
- ficha técnica
- logística
- garantia
- outras ofertas

Também:
- aceita MLB123... e MLB-123...
- aceita até 8 links, um por linha
- um anúncio com erro não interrompe o lote
- sem iPhone/Atalhos
