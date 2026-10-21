# Atividade Prática 7: Blockchain Didática Distribuída
**Disciplina:** Sistemas Distribuídos  

Implementação de uma blockchain distribuída em rede com Proof of Work (PoW), comunicação HTTP entre nós autônomos, simulação de bifurcação (*fork*) e reconciliação distribuída com validação estrita.

---

## Estrutura do Diretório

- `blockchain.py`: Classes `Block` e `Blockchain` com algoritmo de PoW e validação de cadeia.
- `node.py`: Servidor HTTP do nó implementado em FastAPI com endpoints REST (`/chain`, `/mine`, `/peers`, `/resolve`, `/validate`, `/tamper`).
- `demo.py`: Script de automação que inicializa dois nós nas portas 8001 e 8002, conecta os pares, minera blocos, força um fork, executa a reconciliação e testa rejeição de adulteração e nós offline.
- `relatorio_ap7.md`: Relatório técnico com o registro dos testes, tabela comparativa de limitações e respostas às 5 questões conceituais.
- `execucao_ap7.log`: Registro completo da execução dos testes.
- `Conteúdo e Enunciado Atividade Prática 7 - SD.pdf`: Especificação original da atividade.

---

## Como Executar

### Pré-requisitos
* Python 3.10 ou superior.
* Instalar dependências básicas:
  ```bash
  pip install fastapi uvicorn requests pydantic
  ```

### Demonstração Automatizada Completa
Para executar todo o ciclo de testes (nós, mineração, fork, reconciliação e tolerância a falhas) com um único comando:

```bash
python demo.py
```

### Execução Manual com Dois Nós
Caso queira subir e interagir com os nós manualmente:

1. **Terminal 1 (Nó 1):**
   ```bash
   uvicorn node:app --port 8001
   ```

2. **Terminal 2 (Nó 2):**
   ```bash
   uvicorn node:app --port 8002
   ```

3. **Registrar peers:**
   * Conectar Nó 1 ao Nó 2:
     ```bash
     curl -X POST "http://127.0.0.1:8001/peers" -H "Content-Type: application/json" -d "{\"url\": \"http://127.0.0.1:8002\"}"
     ```
   * Conectar Nó 2 ao Nó 1:
     ```bash
     curl -X POST "http://127.0.0.1:8002/peers" -H "Content-Type: application/json" -d "{\"url\": \"http://127.0.0.1:8001\"}"
     ```

4. **Minerar bloco:**
   ```bash
   curl -X POST "http://127.0.0.1:8001/mine" -H "Content-Type: application/json" -d "{\"origem\": \"Alice\", \"destino\": \"Bob\", \"valor\": 50.0}"
   ```

5. **Reconciliar cadeias:**
   ```bash
   curl -X POST "http://127.0.0.1:8002/resolve"
   ```

---

## Checklist de Requisitos da AP7

- [x] Estrutura `Block` e bloco Gênese implementados.
- [x] Proof of Work com meta de dificuldade de zeros funcional.
- [x] Dois nós autônomos executados em portas de rede distintas.
- [x] Registro e comunicação P2P via HTTP REST.
- [x] Geração e comprovação de fork controlado.
- [x] Algoritmo `/resolve` com validação prévia e adoção da maior cadeia válida.
- [x] Detecção e rejeição de cadeia com adulteração forjada.
- [x] Resiliência a nós offline sem interrupção do serviço.
- [x] Tabela de limitações e respostas às 5 questões no relatório técnico.
