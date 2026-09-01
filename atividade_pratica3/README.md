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

**1. Desacoplamento:** Como a arquitetura orientada a eventos e o uso do MQTT proporcionam desacoplamento espacial e temporal neste projeto?
*Resposta:* [Espaço para resposta]

**2. Qualidade de Serviço (QoS):** Quais foram as diferenças observadas (em perda de pacotes e tempo de entrega) entre os 3 níveis de QoS implementados?
*Resposta:* [Espaço para resposta]

**3. Duplicatas:** Em qual nível de QoS ocorreu o recebimento de mensagens duplicadas? Por que isso acontece protocolarmente?
*Resposta:* [Espaço para resposta]

**4. Retained Messages:** Como o uso de mensagens retidas provou ser útil para componentes que inicializam tardiamente no sistema?
*Resposta:* [Espaço para resposta]

**5. Ponto Único de Falha:** O broker representa um ponto único de falha nesta arquitetura? Quais as possíveis soluções para contornar este problema em ambientes reais?
*Resposta:* [Espaço para resposta]
