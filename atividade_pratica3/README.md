# AP3 — Sistemas Distribuídos: MQTT Casa Inteligente

Sistema de monitoramento IoT distribuído usando protocolo MQTT, Docker e Python 3.10+.

## Arquitetura

```
                         ┌─────────────────────────────────┐
                         │   Broker Mosquitto (Docker:1883) │
                         └────────────────┬────────────────┘
                                          │
             ┌────────────────────────────┼────────────────────────────┐
             │                            │                            │
    ┌────────▼────────┐        ┌──────────▼──────────┐     ┌──────────▼──────────┐
    │ pub_temperatura │        │     sub_alarme       │     │   sub_dashboard     │
    │ (sala/temp)     │        │ (porta + status)     │     │ (casa/#  wildcard)  │
    │ QoS 0/1/2       │        │ Detecta LWT e perdas │     │ Dashboard global    │
    └─────────────────┘        └─────────────────────┘     └─────────────────────┘
    ┌────────────────┐
    │   pub_porta    │ ─── LWT ──► casa/status/sensores
    │ (frente/porta) │ ─── Retained (último estado)
    │ QoS 0/1/2      │
    └────────────────┘
```

## Pré-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows)
- Python 3.10+
- Git (opcional)

## Instalação

```powershell
# 1. Entrar no diretório do projeto
cd atividade_pratica3

# 2. Criar e ativar ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependências Python
pip install -r requirements.txt

# 4. Instalar matplotlib para análise (experimentos)
pip install matplotlib pandas
```

## Execução

### Passo 1: Subir o Broker MQTT

```powershell
cd broker
docker compose up -d
docker ps  # verificar se mqtt_broker_ap3 está UP
cd ..
```

### Passo 2: Executar todos os experimentos automaticamente

```powershell
cd experiments
python run_experiment.py --count 60 --interval 1.0
```

Esse comando executa todos os 5 cenários em sequência e gera os CSVs em `experiments/results/`.

### Passo 3: Gerar análise e gráficos

```powershell
cd analysis
python analyze.py
```

Outputs gerados em `analysis/output/`:
- `tabela_resultados.md`
- `grafico_perdas.png`
- `grafico_taxa.png`

### Execução manual (alternativa — terminais separados)

```powershell
# Terminal 1: Dashboard (subscriber global)
cd src && python sub_dashboard.py --qos 1 --timeout 120

# Terminal 2: Central de Alarme (subscriber específico)
cd src && python sub_alarme.py --qos 1 --timeout 120

# Terminal 3: Publisher temperatura
cd src && python pub_temperatura.py --qos 1 --count 60

# Terminal 4: Publisher porta
cd src && python pub_porta.py --qos 1 --count 20

# Para testar LWT (falha controlada):
cd src && python pub_porta.py --qos 1 --count 20 --simulate-crash
```

## Cenários de Experimento

| # | Cenário | QoS | Feature MQTT |
|---|---------|-----|--------------|
| 1 | Baseline | 0 | Fire and Forget |
| 2 | Baseline | 1 | At Least Once |
| 3 | Baseline | 2 | Exactly Once |
| 4 | Falha Controlada | 1 | LWT (Last Will and Testament) |
| 5 | Subscriber Tardio | 1 | Retained Messages |

## Taxonomia de Tópicos

```
casa/
├── sala/temperatura      → float (°C)
├── frente/porta          → "Aberta" | "Fechada"  [RETAINED]
└── status/sensores       → LWT automático do sensor de porta
```

## Estrutura do Payload

```json
{
  "id":        "sensor_temperatura_sala",
  "seq":       42,
  "timestamp": "2026-08-31T20:00:00Z",
  "dado":      24.5,
  "unidade":   "°C",
  "qos_used":  1
}
```

## Derrubar o Broker

```powershell
cd broker
docker compose down
```

## Questões para Análise

**1. Desacoplamento:** O que exatamente foi desacoplado pelo broker?
*Resposta:* O MQTT proporciona **desacoplamento espacial**, pois os produtores (publishers) e consumidores (subscribers) não precisam conhecer o endereço IP (ou a existência) uns dos outros, comunicando-se unicamente através do Broker central via tópicos lógicos. Além disso, fornece um nível de **desacoplamento temporal**: quem publica e quem consome não precisam estar conectados ao broker no mesmo exato momento para que a mensagem tenha efeito, algo acentuado pelo uso de *Retained Messages* e sessões persistentes, permitindo que a entrega seja assíncrona e eventual.

**2. Qualidade de Serviço (QoS):** QoS escolhido é suficiente para o requisito do domínio?
*Resposta:* 
- **Foi Suficiente?** Os testes foram feitos com os 3 níveis para comparação, apenas o último tendo confiança total, com maior sobrecarga da rede. Para esse contexto o QoS 1 já seria aceitável.

- **QoS 0 (Fire and Forget):** Apresentou a menor latência e overhead de rede, pois não há handshake, mas possibilita a perda de pacotes caso a rede esteja instável ou o broker desconecte, já que não há confirmação de entrega.
- **QoS 1 (At Least Once):** Mitigou as perdas garantindo a chegada das mensagens através da resposta de reconhecimento (`PUBACK`), aumentando moderadamente a latência. No entanto, introduziu o fenômeno de **duplicatas** na recepção.
- **QoS 2 (Exactly Once):** Apresentou o maior tempo de latência e processamento devido ao rigoroso *handshake* de 4 vias (PUBREC, PUBREL, PUBCOMP), assegurando entrega confiável, sem perdas e filtrando duplicatas direto na camada de transporte, à custa de maior consumo de rede.

**3. Duplicatas:** Como o sistema identifica mensagem duplicada?
*Resposta:* O recebimento de duplicatas ocorreu no **QoS 1**. Isso ocorre e é identificado quando o emissor mantém a mensagem armazenada até que o pacote de confirmação (`PUBACK`) retorne. Se houver lentidão na rede ou o `PUBACK` se perder, o emissor esgota o timeout e retransmite a mesma mensagem com a flag DUP ativa. O subscriber, não sabendo do problema, processa novamente a mesma mensagem. A injeção da chave sequencial (`seq`) no payload JSON em nosso projeto nos permitiu identificar essa duplicata em nível de aplicação e evitar dados corrompidos.

**4. Retained Messages:** Quando retained é apropriado e quando é perigoso?
*Resposta:* As mensagens retidas instruem o broker a guardar permanentemente a "última imagem" de um tópico. Foi útil porque, no caso do Dashboard (Subscriber) que conectou-se de forma tardia (cenário 5), ele não precisou aguardar uma nova alteração física no sensor da porta para saber o seu estado atual. Ele recebeu o status `Aberta` (ou `Fechada`) imadiatamente no momento do `subscribe`, acelerando drasticamente o sincronismo inicial das aplicações. Essa estratégia pode ser perigosa em cenários mais críticos onde mensagens desatualizadas retidas podem imprimir um diagnóstico incorreto da situação e implicar em uma ação incorreta do Subscriber.

**5. Ponto Único de Falha:** O que acontece se o broker se tornar ponto único de falha?
*Resposta:* Como toda a arquitetura é baseada em topologia de estrela (Publish-Subscribe centralizado), o Broker Mosquitto em execução no Docker compõe um SPOF (Single Point of Failure). Se ele for desligado, nenhum nó se comunica. Em ambientes de produção reais, este risco é contornado através do uso de **Clusterização (HA)** - onde múltiplos brokers trabalham balanceando carga e replicando dados entre si - e usando mecanismos de **Bridging**, que distribuem árvores de tópicos MQTT em redes espalhadas geograficamente para extrema resiliência.
