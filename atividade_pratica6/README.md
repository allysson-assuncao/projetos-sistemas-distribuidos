# Atividade Prática 6 (AP6) — Sistemas Distribuídos
## Exploração de Integridade, Replicação e Consenso

Este repositório contém a implementação completa, o código executável dos experimentos e o relatório técnico da **Atividade Prática 6 (AP6)** da disciplina de Sistemas Distribuídos.

---

## 📂 Estrutura do Diretório

```
atividade_pratica6/
├── Conteúdo e Enunciado Atividade Prática 6 - SD.pdf  # Enunciado original da disciplina
├── ap6_experimento.py                                  # Script executável único com todos os experimentos
├── relatorio_ap6.md                                   # Relatório técnico completo (tabelas, diagrama, respostas)
└── README.md                                          # Este arquivo de instruções
```

---

## 🚀 Como Executar os Experimentos

### Pré-requisitos
* **Python 3.10 ou superior**.
* Nenhuma biblioteca externa é necessária (utiliza exclusivamente a biblioteca padrão do Python: `hashlib`, `json`, `dataclasses`, `copy`, `sys`).

### Comando de Execução
No terminal (PowerShell, Bash ou CMD), navegue até a pasta `atividade_pratica6` e execute:

```powershell
python ap6_experimento.py
```

---

## 🧪 O que o Script Executa

O script executa de forma sequencial e automatizada todos os requisitos estipulados no roteiro mínimo da AP6:

1. **Etapa 1 — Construção da Cadeia Canônica:**
   * Cria o bloco Gênesis (#0) e gera sequencialmente **20 blocos** com transações sintéticas estruturadas.
   * Emite os hashes SHA-256 de referência e valida a cadeia íntegra.

2. **Etapa 2 — Efeito Avalanche:**
   * Altera exatamente **1 caractere** no payload do Bloco #5.
   * Calcula a divergência em nível de caracteres hexadecimais (90.6%) e bits via distância de Hamming (46.9%).

3. **Etapa 3 — Adulteração sem Recálculo:**
   * Modifica o valor da transação do Bloco #10.
   * Demonstra a falha imediata da função `is_valid()` ao verificar a quebra de integridade e encadeamento.

4. **Etapa 4 — Falsificação Local com Recálculo:**
   * Recalcula sequencialmente os hashes dos blocos #10 a #20.
   * Demonstra que a cadeia se torna **internamente consistente e 100% válida localmente**, provando empiricamente por que a validação de hash isolada não impede reescrita de histórico.

5. **Etapa 5 — Réplicas Divergentes (Fork) e Reconciliação:**
   * Simula a bifurcação da cadeia a partir do Bloco #10 em duas réplicas independentes (Réplica A com 16 blocos e Réplica B com 19 blocos).
   * Ambas são válidas localmente, mas incompatíveis entre si.
   * Aplica a regra de reconciliação distribuída (*Longest Chain Rule*) demonstrando a reorganização automática do Nó A para adotar o ramo mais longo do Nó B.

---

## 📄 Relatório Técnico e Respostas

O relatório técnico completo com todas as tabelas de evidências, comparação dos hashes antes/depois, diagrama visual do *fork* em Mermaid e a redação dissertativa *"Hash não é consenso"* com as 4 questões de análise respondidas está disponível em:

👉 [`relatorio_ap6.md`](atividade_pratica6\relatorio_ap6.md)

---

## 📋 Checklist de Entrega

- [x] Cadeia implementada com 20 ou mais blocos gerados dinamicamente.
- [x] Teste de efeito avalanche (alteração de 1 caractere demonstrada e quantificada).
- [x] Adulteração de bloco intermediário sem recálculo com detecção de falha.
- [x] Adulteração de bloco intermediário com recálculo sequencial demonstrando validade local.
- [x] Simulação de réplicas divergentes (*fork*).
- [x] Regra de reconciliação implementada e limitações discutidas criticamente.
- [x] Tabela de experimentos e logs reais dos hashes consolidados.
- [x] Diagrama das duas réplicas divergentes.
- [x] Texto analítico respondendo formalmente às 4 questões sobre consenso distribuído.
