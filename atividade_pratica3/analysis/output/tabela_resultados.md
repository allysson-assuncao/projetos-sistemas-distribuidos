# Tabela de Resultados — Experimentos MQTT Casa Inteligente

| QoS | Semântica | Enviadas | Recebidas | Perdas | Duplicatas | Eventos LWT | Taxa de Entrega |
|-----|-----------|----------|-----------|--------|------------|-------------|-----------------|
| 0 | Fire and Forget | 60 | 60 | 0 | 0 | 0 | 100.0% |
| 1 | At Least Once | 60 | 60 | 0 | 0 | 0 | 100.0% |
| 2 | Exactly Once | 60 | 60 | 0 | 0 | 0 | 100.0% |
| 1 | Falha c/ LWT | 30 | 31 | 0 | 1 | 2 | 103.3% |
