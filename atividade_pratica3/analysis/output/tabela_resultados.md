# Tabela de Resultados — Experimentos MQTT Casa Inteligente

| QoS | Semântica | Enviadas | Recebidas | Perdas | Duplicatas | Eventos LWT | Taxa de Entrega |
|-----|-----------|----------|-----------|--------|------------|-------------|-----------------|
| 0 | Fire and Forget | 60 | 2 | 4 | 0 | 1 | 3.3% |
| 1 | At Least Once | 60 | 2 | 4 | 0 | 1 | 3.3% |
| 2 | Exactly Once | 60 | 2 | 4 | 0 | 1 | 3.3% |
| 1 | Falha c/ LWT | 60 | 33 | 0 | 2 | 2 | 55.0% |
