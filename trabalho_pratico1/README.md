# Trabalho Prático 1 - SD
Estufa Agrícola Automatizada — Sistema Distribuído com MQTT e XML-RPC

Este projeto implementa um sistema distribuído para controle de uma estufa agrícola. Ele utiliza uma combinação de mensageria assíncrona pub/sub (MQTT) e chamadas síncronas de método remoto (XML-RPC).

## Arquitetura do Sistema

A arquitetura foi atualizada para corrigir problemas de dependência circular e falta de coordenação entre os controladores. O Middleware agora opera de forma autônoma como um servidor isolado.

```mermaid
graph TD
    Client[Cliente (Dumb)] -->|XML-RPC :9000| Middleware[Middleware Server]
    Middleware -->|XML-RPC :8001| Ctrl1[Controlador 1]
    Middleware -->|XML-RPC :8002| Ctrl2[Controlador 2]
    Middleware -->|XML-RPC :8003| Ctrl3[Controlador 3]
    
    Ctrl1 -->|MQTT| Broker[(Mosquitto Broker :1883)]
    Ctrl2 -->|MQTT| Broker
    Ctrl3 -->|MQTT| Broker
    
    Sensor[Sensores] -->|MQTT| Broker
    Broker -->|MQTT| Actuator[Atuadores (Deduplicação LRU)]
```

### Componentes

| Componente | Descrição |
|---|---|
| **Broker MQTT** | Eclipse Mosquitto (Docker). Central de mensagens para sensores e atuadores. |
| **Sensores** | Publicam dados simulados de temperatura e umidade via MQTT. |
| **Controladores (x3)** | Recebem dados MQTT, tomam decisões e expõem estado/ações via XML-RPC. |
| **Middleware Server** | Novo servidor autônomo (porta 9000). Votação majoritária (BFT) centralizada. |
| **Cliente** | Conecta exclusivamente ao Middleware Server. Interface de usuário (CLI). |
| **Atuadores** | Assinam comandos MQTT. Utilizam deduplicação LRU para evitar re-execução. |

## Melhorias e Correções (V2)

1. **Middleware Standalone**: O middleware deixou de ser importado pelo cliente e agora opera em um processo `middleware_server.py` (na porta 9000). Os clientes apenas consultam o servidor.
2. **Transferência de Estado no Boot**: Os controladores agora consultam o Middleware via XML-RPC durante a sua inicialização (antes de assinar tópicos MQTT) para sincronizar seu arquivo JSON com o estado real e aprovado pelo cluster.
3. **Deduplicação de Comandos**: As decisões autônomas dos controladores geram um `comando_id` determinístico (hash do timestamp original do sensor MQTT + a ação). Isso permite que o Atuador use um cache LRU para descartar as redundâncias de rede e não processar a mesma ação várias vezes (já que existem 3 controladores enviando o mesmo evento).

## Como Executar

É essencial respeitar a **Ordem de Inicialização**, para que os Controladores consigam sincronizar seu estado através do Middleware durante o boot.

Você pode usar os scripts automatizados `scripts/start_all.sh` ou `scripts/start_all.ps1`. Ou siga manualmente:

1. **Broker MQTT**:
   ```bash
   docker compose up -d
   ```
2. **Middleware Server** (Obrigatório antes dos controladores):
   ```bash
   python -m estufa.middleware_server
   ```
3. **Controladores**:
   ```bash
   python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json
   python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json
   python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json
   ```
4. **Atuador & Sensor**:
   ```bash
   python -m estufa.atuador
   python -m estufa.sensor --modo normal
   ```
5. **Cliente**:
   ```bash
   python -m estufa.cliente
   ```

## Testes Automatizados

O sistema conta com testes de deduplicação, lógica interna e integração.
Para rodar os testes:
```bash
pytest tests/ -v
```
