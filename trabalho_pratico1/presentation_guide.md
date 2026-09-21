# Guia de Apresentação — Trabalho Prático 1: Sistemas Distribuídos
## Estufa Agrícola Automatizada: MQTT + XML-RPC

> **Público:** Aluno (uso pessoal durante a apresentação ao professor)  
> **Duração estimada da apresentação:** 15–20 minutos  
> **Modo:** Demonstração ao vivo com terminais reais

---

## 🖥️ Preparação do Ambiente (Antes da Apresentação)

### Pré-requisitos

Certifique-se de ter instalado e funcionando:

- [ ] **Docker Desktop** em execução (ícone aparece na bandeja do sistema)
- [ ] **Python 3.10+** instalado (`python --version`)
- [ ] **Dependências instaladas:** `pip install -r requirements.txt`
- [ ] **Terminal multiplexer:** Use um dos abaixo para gerenciar vários painéis

### Configuração dos Terminais (Windows — Recomendado: Windows Terminal)

O **Windows Terminal** suporta abas e painéis divididos nativamente.

**Abrir 8 painéis/abas:**

1. Abra o Windows Terminal
2. Para cada processo abaixo, abra uma nova aba (`Ctrl+Shift+T`) ou divida o painel (`Alt+Shift++` para vertical, `Alt+Shift+-` para horizontal)
3. Em cada painel, navegue para a pasta do projeto:
   ```powershell
   cd C:\Users\anybo\Documents\Projects\projetos-sistemas-distribuidos\trabalho_pratico1
   ```

**Layout sugerido (8 terminais):**

```
┌──────────────────┬─────────────────┐
│  T1: Broker      │  T2: Middleware  │
├──────────────────┼─────────────────┤
│  T3: Ctrl 1      │  T4: Ctrl 2     │
├──────────────────┼─────────────────┤
│  T5: Ctrl 3      │  T6: Atuador    │
├──────────────────┼─────────────────┤
│  T7: Sensor      │  T8: Cliente    │
└──────────────────┴─────────────────┘
```

**Alternativa (Linux/macOS):** Use `tmux` com o layout:
```bash
# Criar sessão tmux com 8 painéis
tmux new-session -s estufa
# Dividir painéis: Ctrl+B % (vertical) | Ctrl+B " (horizontal)
```

---

## 🚀 Roteiro de Inicialização (Ordem Obrigatória)

Execute cada comando no terminal correspondente na ordem abaixo:

### Passo 1 — Terminal 1: Broker MQTT

```bash
docker compose up -d
docker ps  # Verifique: estufa_mqtt_broker com status "Up"
```

**O que explicar:** "O broker Mosquitto é o backbone de mensagens. Todos os sensores publicam aqui e os controladores e atuadores se inscrevem."

---

### Passo 2 — Terminal 2: Middleware Server

```bash
python -m estufa.middleware_server
```

**Saída esperada:**
```
[MIDDLEWARE SERVER] 🚀 Iniciando em localhost:9000
[MIDDLEWARE SERVER] Orquestrando 3 controladores:
  - ctrl_1 @ localhost:8001
  - ctrl_2 @ localhost:8002
  - ctrl_3 @ localhost:8003
[MIDDLEWARE SERVER] Aguardando conexões de clientes em http://localhost:9000
```

**O que explicar:** "O Middleware é o ponto de entrada único para o cliente. Ele encapsula toda a lógica de tolerância a falhas. O cliente nunca sabe quantos controladores existem ou quais estão online."

---

### Passo 3 — Terminais 3, 4, 5: Controladores (em paralelo)

**Terminal 3:**
```bash
python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json
```

**Terminal 4:**
```bash
python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json
```

**Terminal 5:**
```bash
python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json
```

**Saída esperada em cada controlador:**
```
[ctrl_1] XML-RPC server iniciado em localhost:8001
[ctrl_1] 🔄 Iniciando sincronização de estado via Middleware (http://localhost:9000)...
[ctrl_1] ✅ Estado sincronizado com sucesso (tentativa 1/10).
[ctrl_1] ✅ Controlador totalmente inicializado. Consumindo sensores MQTT.
```

**O que explicar:** "Observe a sincronização de estado no boot — cada controlador consulta o Middleware para obter o estado atual do cluster antes de começar a processar dados. Isso implementa o padrão **State Transfer**."

---

### Passo 4 — Terminal 6: Atuador

```bash
python -m estufa.atuador
```

**O que explicar:** "O atuador assina os tópicos de comando MQTT. O cache LRU está ativo — ele vai descartar as 2 cópias duplicadas do mesmo comando que chegarem dos outros 2 controladores."

---

### Passo 5 — Terminal 7: Sensor (modo normal)

```bash
python -m estufa.sensor --modo normal
```

**O que explicar:** "O sensor publica temperatura e umidade a cada 2 segundos. No modo normal, os valores ficam dentro dos limiares — nenhum atuador deve ser acionado."

---

### Passo 6 — Terminal 8: Cliente

```bash
python -m estufa.cliente
```

**O que explicar:** "O cliente conecta exclusivamente ao Middleware Server na porta 9000. Nunca há comunicação direta com os controladores."

---

## 🔥 Teste 1: Deduplicação LRU (Sensor Automático)

**Cenário:** Demonstrar que os 3 controladores processam o mesmo evento MQTT e apenas 1 comando físico é executado.

### Passo a passo:

1. **Parar o sensor** (Terminal 7): `Ctrl+C`

2. **Iniciar sensor em modo SECO** (força ativação da bomba):
   ```bash
   python -m estufa.sensor --modo seco
   ```

3. **Observar nos Terminais 3, 4 e 5** (controladores):
   ```
   [ctrl_1] 💧 Umidade=18.3% < 30.0% → LIGAR bomba
   [ctrl_2] 💧 Umidade=18.3% < 30.0% → LIGAR bomba
   [ctrl_3] 💧 Umidade=18.3% < 30.0% → LIGAR bomba
   ```

4. **Observar no Terminal 6** (atuador):
   ```
   [ATUADOR] 💧 Bomba de Irrigação → LIGADA (origem: ctrl_1)
   [ATUADOR] 🔁 Comando duplicado ignorado: a1b2c3d4... (tópico: estufa/atuadores/bomba)
   [ATUADOR] 🔁 Comando duplicado ignorado: a1b2c3d4... (tópico: estufa/atuadores/bomba)
   ```

**O que enfatizar:** "Os 3 controladores geraram o **mesmo hash MD5** para o mesmo evento de sensor (mesmo timestamp). O atuador processou apenas o primeiro e descartou os outros 2 como duplicatas."

---

## 💥 Teste 2: Tolerância a Crash (Falha e Recuperação)

**Cenário:** Matar um controlador e demonstrar que o sistema continua funcionando com quórum 2/3.

### Passo a passo:

1. **No Terminal 5** (ctrl_3): pressione `Ctrl+C` para matar o processo.

2. **No Terminal 2** (Middleware): observe o log de falha na próxima operação.

3. **No Terminal 8** (cliente): execute qualquer operação:
   - Opção 1: Consultar estado
   - Opção 2: Ligar bomba manualmente

4. **Observe no Terminal 2:**
   ```
   [MIDDLEWARE] ⚠️  Controlador ctrl_3 falhou: [Errno 111] Connection refused
   [MIDDLEWARE] Votos: {"estado_honesto": 2} | Quorum mínimo: 2
   ```

5. **Reiniciar ctrl_3** no Terminal 5:
   ```bash
   python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json
   ```

6. **Observe a sincronização:**
   ```
   [ctrl_3] 🔄 Iniciando sincronização de estado via Middleware...
   [ctrl_3] ✅ Estado sincronizado com sucesso.
   ```

**O que enfatizar:** "Com 1 controlador offline, o sistema manteve disponibilidade através do quórum 2/3. Quando ctrl_3 voltou, ele sincronizou automaticamente com o estado atual do cluster — isso é **State Transfer**."

---

## 👾 Teste 3: Tolerância a Falhas Byzantinas

**Cenário:** Substituir ctrl_2 por uma réplica com comportamento arbitrário malicioso.

### Passo a passo:

1. **No Terminal 4** (ctrl_2 normal): pressione `Ctrl+C`.

2. **Reiniciar ctrl_2 em modo Byzantino:**
   ```bash
   python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino
   ```

3. **Observe no Terminal 4** a mensagem de modo Byzantino:
   ```
   [ctrl_2] XML-RPC server iniciado em localhost:8002 [MODO BYZANTINO]
   ```

4. **No Terminal 8** (cliente): consulte o estado atual.

5. **Observe no Terminal 2** (Middleware):
   ```
   [MIDDLEWARE] Votos: {
     "estado_honesto_ctrl1_ctrl3": 2,
     "temperatura=999_byzantino": 1
   }
   [MIDDLEWARE] Quorum mínimo: 2 → Resultado honesto aprovado
   ```

6. **Verifique no cliente:** O estado retornado é o honesto (temperatura real, não 999°C).

**O que enfatizar:** "ctrl_2 está retornando temperatura=999°C e estados invertidos. Mas os outros 2 controladores concordam com o estado real. A votação por maioria neutraliza o comportamento malicioso — o cliente nunca vê o dado corrupto."

---

## 🧪 Executar Testes Automatizados (se solicitado)

```bash
# Em qualquer terminal (sem precisar de broker ou controladores)
cd C:\Users\anybo\Documents\Projects\projetos-sistemas-distribuidos\trabalho_pratico1

# Todos os testes
pytest tests/ -v

# Por módulo
pytest tests/test_controlador.py -v   # Lógica de decisão + IDs determinísticos
pytest tests/test_middleware.py -v    # Votação BFT com mocks
pytest tests/test_atuador.py -v       # Cache LRU deduplicação
```

---

## 📋 Perguntas Frequentes do Professor

**P: Por que usar MQTT e não apenas XML-RPC para tudo?**
R: MQTT é ideal para dados de sensores — leve, pub/sub desacoplado, tolerante a conexões intermitentes. XML-RPC é ideal para comandos síncronos onde precisamos de confirmação e aplicação de votação. Os dois protocolos complementam: MQTT para fluxo de dados, XML-RPC para controle.

**P: Como o sistema sabe que um controlador está Byzantino?**
R: Ele não sabe especificamente. A votação por maioria torna o comportamento Byzantino irrelevante — o resultado honesto sempre prevalece enquanto ≥2 controladores forem honestos.

**P: O que acontece se o Middleware cair?**
R: O Middleware é um ponto de falha nesta implementação. Em produção, o Middleware também seria replicado (ex.: usando Raft ou Paxos para eleição de líder). Para este trabalho, o Middleware sendo um servidor standalone centralizado é uma simplificação consciente.

**P: O que é o `sensor_timestamp` e por que ele garante o mesmo hash?**
R: Quando o sensor publica uma leitura MQTT, inclui `"timestamp": time.time()` no payload JSON. Todos os 3 controladores recebem **a mesma mensagem** (mesmo bytes, mesmo JSON, mesmo timestamp). Portanto, `MD5("bomba_ligar_1700000042.999")` produz o mesmo hex em todos os 3 processos.

---

## ⏱️ Cronograma Sugerido da Apresentação

| Tempo | Atividade |
|---|---|
| 0–2 min | Apresentação da arquitetura (diagrama no README) |
| 2–5 min | Inicialização dos componentes (Passos 1–6) |
| 5–8 min | Demonstração do sistema funcionando normalmente |
| 8–11 min | **Teste 1:** Deduplicação LRU (sensor modo seco) |
| 11–14 min | **Teste 2:** Crash de ctrl_3 + recuperação com State Transfer |
| 14–17 min | **Teste 3:** Modo Byzantino + votação por maioria |
| 17–20 min | Testes automatizados + perguntas |
