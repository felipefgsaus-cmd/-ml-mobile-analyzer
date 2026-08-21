# ML Analyzer V8.2

Correções:
- aceita links com MLB-123... e MLB123...
- analisa vários links, um por linha
- um anúncio com erro não derruba o restante do lote
- quando o link contém apenas o ID do anúncio, tenta descobrir automaticamente o catalog_product_id
- usa secondary_key das avaliações como fonte principal do ID de catálogo
- também tenta /items/{id} e Multi-GET /items como fallback
- com o ID de catálogo recuperado, volta a buscar título, fotos, ficha técnica, descrição e outras ofertas
- sem integração com iPhone/Atalhos
