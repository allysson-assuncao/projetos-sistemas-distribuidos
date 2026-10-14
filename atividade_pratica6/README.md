# Atividade Prática 6: Integridade, Replicação e Consenso
**Disciplina:** Sistemas Distribuídos  

Implementação e análise experimental da relação entre integridade criptográfica local (hashing) e consenso distribuído global.

---

## Estrutura do Diretório

- `ap6_experimento.py`: Script com a implementação da cadeia didática e execução dos testes.
- `relatorio_ap6.md`: Relatório técnico com tabelas de evidência, diagrama de bifurcação e respostas teóricas.
- `Conteúdo e Enunciado Atividade Prática 6 - SD.pdf`: Especificação da atividade.

---

## Como Executar

### Pré-requisitos
* Python 3.10 ou superior.
* Não requer instalação de pacotes externos (utiliza exclusivamente a biblioteca padrão do Python).

### Execução dos Testes
No terminal, a partir da pasta deste repositório, execute:

```bash
python ap6_experimento.py
```

O script executa de forma sequencial:
1. Construção da cadeia inicial com 20 blocos gerados dinamicamente.
2. Demonstração do efeito avalanche (alteração pontual de 1 caractere no bloco 5).
3. Adulteração de bloco intermediário (#10) sem recálculo, evidenciando a quebra de integridade.
4. Adulteração do bloco #10 com recálculo sequencial dos hashes posteriores, evidenciando a consistência local forjada.
5. Simulação de réplicas divergentes (*fork*) e resolução pela regra da maior cadeia (*Longest Chain Rule*).

---

## Relatório e Entregáveis

O relatório detalhado com os dados de execução, tabela comparativa de hashes, diagrama em Mermaid e as respostas às questões de análise sobre consenso está disponível em:
[`relatorio_ap6.md`](relatorio_ap6.md).
