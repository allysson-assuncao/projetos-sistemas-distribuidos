# Plano de Implementação — Trabalho Prático 1 (SD)
## Estufa Agrícola Automatizada — Sistema Distribuído com MQTT e XML-RPC

---

## Visão Geral

Sistema distribuído de controle de estufa agrícola com:
- **Broker MQTT** (Eclipse Mosquitto via Docker): barramento pub/sub para sensores e atuadores
- **Sensores** (processos Python): publicam temperatura e umidade do solo via MQTT
- **Atuadores** (processos Python): assinam tópicos e ativam bomba d'água e exaustor
- **3 Controladores** (processos Python + XML-RPC Server): consomem dados MQTT, tomam decisões, persistem estado em JSON e expõem métodos remotos via XML-RPC
- **Middleware** (módulo Python): invoca métodos nos 3 controladores via XML-RPC, implementa votação por maioria simples (2 de 3) para tolerância a falhas Bizantinas e tolera queda de 1 controlador
- **Cliente** (processo Python): interface de linha de comando que chama o middleware para consultar e comandar a estufa

### Decisões de Design Adotadas
| Componente | Tecnologia |
|---|---|
| Broker MQTT | Eclipse Mosquitto (Docker) |
| Comunicação Sensor↔Controlador | MQTT pub/sub |
| Comunicação Cliente↔Controlador | XML-RPC (xmlrpc.client + xmlrpc.server nativos Python) |
| Réplicas | 1 principal + 2 réplicas (3 nós totais) |
| Consenso | Votação por maioria simples (2 de 3) |
| Armazenamento | Arquivo JSON por controlador |
| Execução | Subprocessos Python separados |
| Testes | pytest com broker Mosquitto via Docker |

---

## Estrutura Final de Arquivos

```
trabalho_pratico1/
│
├── docker-compose.yml              # Sobe o broker Mosquitto
├── mosquitto/
│   └── mosquitto.conf              # Configuração do broker
│
├── requirements.txt                # paho-mqtt, pytest
│
├── estufa/                         # Pacote principal
│   ├── __init__.py
│   ├── config.py                   # Constantes globais (tópicos, portas, thresholds)
│   ├── sensor.py                   # Processo sensor (publica temp/umidade)
│   ├── atuador.py                  # Processo atuador (assina e executa ações)
│   ├── controlador.py              # Processo controlador (XML-RPC server + MQTT sub)
│   ├── middleware.py               # Middleware: XML-RPC client com votação majoritária
│   └── cliente.py                  # CLI do usuário final
│
├── tests/
│   ├── __init__.py
│   ├── test_middleware.py          # Testes do middleware (votação, BFT, queda de réplica)
│   ├── test_controlador.py         # Testes do controlador (lógica de decisão, persistência)
│   └── test_integracao.py          # Testes end-to-end com broker real
│
├── scripts/
│   ├── start_all.ps1               # Inicia todos os processos (Windows)
│   ├── start_all.sh                # Inicia todos os processos (Linux/macOS)
│   └── demo_byzantino.py           # Script de demonstração de falha Bizantina
│
├── relatorio/
│   └── relatorio.md                # Relatório do trabalho
│
└── README.md
```

---

## Fase 1 — Infraestrutura Base e Configuração

**Agente responsável:** Fase 1  
**Pré-requisitos:** Docker instalado e rodando; Python 3.9+

### 1.1 — Arquivo `docker-compose.yml`

Criar `trabalho_pratico1/docker-compose.yml` com o conteúdo **exato**:

```yaml
version: "3.8"

services:
  mosquitto:
    image: eclipse-mosquitto:2.0
    container_name: estufa_mqtt_broker
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf
    restart: unless-stopped
```

### 1.2 — Arquivo `mosquitto/mosquitto.conf`

Criar `trabalho_pratico1/mosquitto/mosquitto.conf`:

```
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
```

### 1.3 — Arquivo `requirements.txt`

Criar `trabalho_pratico1/requirements.txt`:

```
paho-mqtt==2.1.0
pytest==8.3.3
pytest-timeout==2.3.1
```

### 1.4 — Arquivo `estufa/__init__.py`

Criar `trabalho_pratico1/estufa/__init__.py` (vazio).

### 1.5 — Arquivo `tests/__init__.py`

Criar `trabalho_pratico1/tests/__init__.py` (vazio).

### 1.6 — Arquivo `scripts/.gitkeep` (garante que pasta exista)

Criar `trabalho_pratico1/scripts/.gitkeep` (vazio).

### 1.7 — Comando de verificação da fase

```powershell
# No diretório trabalho_pratico1/
docker compose up -d
docker ps  # deve mostrar "estufa_mqtt_broker" com status "Up"
docker compose down
```

---

## Fase 2 — Módulo de Configuração Global

**Agente responsável:** Fase 2  
**Pré-requisito:** Fase 1 concluída

### 2.1 — Arquivo `estufa/config.py`

Criar `trabalho_pratico1/estufa/config.py` com o conteúdo **exato**:

```python
"""
config.py — Constantes globais do sistema Estufa Agrícola Distribuída.
Todas as configurações de tópicos MQTT, portas XML-RPC e thresholds de decisão
estão centralizadas aqui para facilitar manutenção e testes.
"""

# ──────────────────────────────────────────────
# MQTT — Broker
# ──────────────────────────────────────────────
MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

# ──────────────────────────────────────────────
# MQTT — Tópicos
# ──────────────────────────────────────────────
TOPIC_TEMPERATURA   = "estufa/sensores/temperatura"
TOPIC_UMIDADE_SOLO  = "estufa/sensores/umidade_solo"
TOPIC_ATUADOR_BOMBA = "estufa/atuadores/bomba"
TOPIC_ATUADOR_EXAUSTOR = "estufa/atuadores/exaustor"
TOPIC_STATUS_BOMBA  = "estufa/status/bomba"
TOPIC_STATUS_EXAUSTOR = "estufa/status/exaustor"

# ──────────────────────────────────────────────
# XML-RPC — Controladores
# ──────────────────────────────────────────────
# Cada controlador tem uma porta XML-RPC e um ID único.
CONTROLADORES = [
    {"id": "ctrl_1", "host": "localhost", "port": 8001, "data_file": "data_ctrl_1.json"},
    {"id": "ctrl_2", "host": "localhost", "port": 8002, "data_file": "data_ctrl_2.json"},
    {"id": "ctrl_3", "host": "localhost", "port": 8003, "data_file": "data_ctrl_3.json"},
]

# ──────────────────────────────────────────────
# Thresholds de Controle da Estufa
# ──────────────────────────────────────────────
TEMP_MAX_CELSIUS     = 35.0   # Acima disso, ligar exaustor
TEMP_MIN_CELSIUS     = 15.0   # Abaixo disso, desligar exaustor
UMIDADE_MIN_PERCENT  = 30.0   # Abaixo disso, ligar bomba de irrigação
UMIDADE_MAX_PERCENT  = 70.0   # Acima disso, desligar bomba

# ──────────────────────────────────────────────
# Middleware — Parâmetros de votação
# ──────────────────────────────────────────────
TIMEOUT_RPC_SEGUNDOS = 3       # Timeout por chamada XML-RPC
QUORUM_MINIMO        = 2       # Mínimo de respostas concordantes para aceitar resultado
```

---

## Fase 3 — Sensor e Atuador (Camada MQTT)

**Agente responsável:** Fase 3  
**Pré-requisito:** Fase 2 concluída

### 3.1 — Arquivo `estufa/sensor.py`

Criar `trabalho_pratico1/estufa/sensor.py` com o conteúdo **exato**:

```python
"""
sensor.py — Processo Sensor da Estufa.

Simula dois sensores físicos:
  - Sensor de Temperatura (ºC)
  - Sensor de Umidade do Solo (%)

Publica leituras no broker MQTT nos tópicos definidos em config.py.
Pode ser executado diretamente ou importado para testes.

Uso:
    python -m estufa.sensor [--intervalo SEGUNDOS] [--modo {normal,seco,quente,frio}]
"""

import argparse
import json
import random
import time
import paho.mqtt.client as mqtt
from estufa import config


# ─────────────────────────────────────────
# Perfis de simulação pré-configurados
# ─────────────────────────────────────────
PERFIS = {
    "normal": {"temp": (20.0, 30.0), "umidade": (40.0, 65.0)},
    "seco":   {"temp": (25.0, 33.0), "umidade": (10.0, 29.0)},  # dispara bomba
    "quente": {"temp": (36.0, 42.0), "umidade": (35.0, 55.0)},  # dispara exaustor
    "frio":   {"temp": (10.0, 14.0), "umidade": (50.0, 70.0)},  # nenhum atuador
}


def _criar_cliente_mqtt(client_id: str) -> mqtt.Client:
    """Cria e conecta um cliente MQTT ao broker configurado."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    return client


def publicar_leitura(client: mqtt.Client, topico: str, valor: float, unidade: str) -> None:
    """Publica uma leitura de sensor em formato JSON no tópico MQTT."""
    payload = json.dumps({
        "valor": round(valor, 2),
        "unidade": unidade,
        "timestamp": time.time(),
    })
    result = client.publish(topico, payload, qos=1)
    result.wait_for_publish()
    print(f"[SENSOR] {topico}: {payload}")


def executar_sensor(intervalo: float = 2.0, perfil: str = "normal", max_iteracoes: int = None):
    """
    Loop principal do sensor.

    Args:
        intervalo: Intervalo entre publicações em segundos.
        perfil: Um dos perfis em PERFIS (normal, seco, quente, frio).
        max_iteracoes: Se definido, encerra após N publicações (útil para testes).
    """
    client = _criar_cliente_mqtt("sensor_estufa")
    client.loop_start()

    ranges = PERFIS.get(perfil, PERFIS["normal"])
    iteracao = 0

    try:
        while True:
            temperatura = random.uniform(*ranges["temp"])
            umidade = random.uniform(*ranges["umidade"])

            publicar_leitura(client, config.TOPIC_TEMPERATURA, temperatura, "°C")
            publicar_leitura(client, config.TOPIC_UMIDADE_SOLO, umidade, "%")

            iteracao += 1
            if max_iteracoes is not None and iteracao >= max_iteracoes:
                break

            time.sleep(intervalo)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sensor da Estufa Agrícola")
    parser.add_argument("--intervalo", type=float, default=2.0,
                        help="Intervalo entre publicações (segundos)")
    parser.add_argument("--modo", choices=list(PERFIS.keys()), default="normal",
                        help="Perfil de simulação")
    args = parser.parse_args()
    executar_sensor(intervalo=args.intervalo, perfil=args.modo)
```

### 3.2 — Arquivo `estufa/atuador.py`

Criar `trabalho_pratico1/estufa/atuador.py` com o conteúdo **exato**:

```python
"""
atuador.py — Processo Atuador da Estufa.

Assina os tópicos de comando no broker MQTT e simula a execução de:
  - Bomba de irrigação (liga/desliga)
  - Exaustor de temperatura (liga/desliga)

Ao receber um comando, publica no tópico de status confirmando a execução.

Uso:
    python -m estufa.atuador
"""

import json
import time
import paho.mqtt.client as mqtt
from estufa import config

# Estado interno dos atuadores (simulação de hardware)
_estado_bomba    = {"ligado": False}
_estado_exaustor = {"ligado": False}


def _on_connect(client, userdata, flags, reason_code, properties):
    """Callback de conexão: assina os tópicos de comando dos atuadores."""
    if reason_code == 0:
        print("[ATUADOR] Conectado ao broker MQTT.")
        client.subscribe(config.TOPIC_ATUADOR_BOMBA,    qos=1)
        client.subscribe(config.TOPIC_ATUADOR_EXAUSTOR, qos=1)
        print(f"[ATUADOR] Assinando: {config.TOPIC_ATUADOR_BOMBA}")
        print(f"[ATUADOR] Assinando: {config.TOPIC_ATUADOR_EXAUSTOR}")
    else:
        print(f"[ATUADOR] Falha na conexão: {reason_code}")


def _processar_bomba(client: mqtt.Client, payload: dict) -> None:
    """Processa comando da bomba e publica status de confirmação."""
    acao = payload.get("acao", "").lower()
    novo_estado = (acao == "ligar")
    _estado_bomba["ligado"] = novo_estado
    status = "LIGADA" if novo_estado else "DESLIGADA"
    print(f"[ATUADOR] 💧 Bomba de Irrigação → {status}")
    _publicar_status(client, config.TOPIC_STATUS_BOMBA, "bomba", novo_estado)


def _processar_exaustor(client: mqtt.Client, payload: dict) -> None:
    """Processa comando do exaustor e publica status de confirmação."""
    acao = payload.get("acao", "").lower()
    novo_estado = (acao == "ligar")
    _estado_exaustor["ligado"] = novo_estado
    status = "LIGADO" if novo_estado else "DESLIGADO"
    print(f"[ATUADOR] 🌬️ Exaustor → {status}")
    _publicar_status(client, config.TOPIC_STATUS_EXAUSTOR, "exaustor", novo_estado)


def _publicar_status(client: mqtt.Client, topico: str, nome: str, ligado: bool) -> None:
    """Publica confirmação de execução no tópico de status."""
    payload = json.dumps({
        "atuador": nome,
        "ligado": ligado,
        "timestamp": time.time(),
    })
    client.publish(topico, payload, qos=1)


def _on_message(client, userdata, msg):
    """Callback de mensagem: roteia para o handler correto."""
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"[ATUADOR] Payload inválido em {msg.topic}: {msg.payload}")
        return

    if msg.topic == config.TOPIC_ATUADOR_BOMBA:
        _processar_bomba(client, payload)
    elif msg.topic == config.TOPIC_ATUADOR_EXAUSTOR:
        _processar_exaustor(client, payload)


def executar_atuador():
    """Inicia o atuador e aguarda comandos indefinidamente."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="atuador_estufa")
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
    print("[ATUADOR] Aguardando comandos...")
    client.loop_forever()


if __name__ == "__main__":
    executar_atuador()
```

---

## Fase 4 — Controlador (Núcleo do Sistema)

**Agente responsável:** Fase 4  
**Pré-requisito:** Fase 3 concluída

O controlador é o componente mais complexo. Ele:
1. Assina os tópicos MQTT dos sensores e processa os dados
2. Toma decisões e publica comandos para os atuadores
3. Persiste o estado atual em um arquivo JSON
4. Expõe métodos remotos via XML-RPC Server para o middleware

### 4.1 — Arquivo `estufa/controlador.py`

Criar `trabalho_pratico1/estufa/controlador.py` com o conteúdo **exato**:

```python
"""
controlador.py — Controlador de Processo da Estufa.

Responsabilidades:
  1. Subscribes MQTT: recebe leituras de temperatura e umidade.
  2. Lógica de decisão: aciona bomba e exaustor conforme thresholds.
  3. Persistência JSON: salva o estado atual em arquivo local.
  4. Servidor XML-RPC: expõe métodos remotos ao middleware.

Cada instância representa um nó do cluster de controladores.
Três instâncias (portas 8001, 8002, 8003) formam o cluster de 3 réplicas.

Uso:
    python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json
    python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json
    python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json
    
    # Modo Byzantino (para demonstração de falha):
    python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino
"""

import argparse
import json
import os
import threading
import time
from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
import paho.mqtt.client as mqtt
from estufa import config


# ─────────────────────────────────────────
# Estado padrão do sistema
# ─────────────────────────────────────────
ESTADO_INICIAL = {
    "temperatura": None,
    "umidade_solo": None,
    "bomba_ligada": False,
    "exaustor_ligado": False,
    "ultima_atualizacao": None,
    "controlador_id": None,
}


class Controlador:
    """
    Núcleo do controlador de processo da estufa.

    Thread-safe: o lock protege o estado compartilhado entre a thread
    MQTT (escritas) e a thread XML-RPC (leituras).
    """

    def __init__(self, ctrl_id: str, data_file: str, byzantino: bool = False):
        """
        Args:
            ctrl_id: Identificador único deste controlador (ex: 'ctrl_1').
            data_file: Caminho do arquivo JSON de persistência.
            byzantino: Se True, retorna dados deliberadamente errados (simulação de falha).
        """
        self.ctrl_id = ctrl_id
        self.data_file = data_file
        self.byzantino = byzantino
        self._lock = threading.Lock()

        # Carrega estado do disco ou usa o estado inicial
        self._estado = self._carregar_estado()
        self._estado["controlador_id"] = ctrl_id

    # ─── Persistência ───────────────────────────────────────────

    def _carregar_estado(self) -> dict:
        """Lê o estado atual do arquivo JSON. Retorna estado inicial se não existir."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return dict(ESTADO_INICIAL)

    def _salvar_estado(self) -> None:
        """Persiste o estado atual no arquivo JSON (deve ser chamado com lock)."""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self._estado, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"[{self.ctrl_id}] Erro ao salvar estado: {e}")

    # ─── Lógica de Decisão ──────────────────────────────────────

    def _decidir_atuacao(self) -> None:
        """
        Avalia o estado atual e decide se liga/desliga os atuadores.
        Publica comandos via MQTT. Chamado sempre que um sensor atualiza.
        Deve ser chamado com o lock adquirido.
        """
        temp    = self._estado.get("temperatura")
        umidade = self._estado.get("umidade_solo")

        # Decisão: Exaustor (baseado em temperatura)
        if temp is not None:
            if temp > config.TEMP_MAX_CELSIUS and not self._estado["exaustor_ligado"]:
                self._estado["exaustor_ligado"] = True
                self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, "ligar")
                print(f"[{self.ctrl_id}] 🌡️  Temp={temp:.1f}°C > {config.TEMP_MAX_CELSIUS}°C → LIGAR exaustor")
            elif temp < config.TEMP_MIN_CELSIUS and self._estado["exaustor_ligado"]:
                self._estado["exaustor_ligado"] = False
                self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, "desligar")
                print(f"[{self.ctrl_id}] 🌡️  Temp={temp:.1f}°C < {config.TEMP_MIN_CELSIUS}°C → DESLIGAR exaustor")

        # Decisão: Bomba de irrigação (baseado em umidade do solo)
        if umidade is not None:
            if umidade < config.UMIDADE_MIN_PERCENT and not self._estado["bomba_ligada"]:
                self._estado["bomba_ligada"] = True
                self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, "ligar")
                print(f"[{self.ctrl_id}] 💧 Umidade={umidade:.1f}% < {config.UMIDADE_MIN_PERCENT}% → LIGAR bomba")
            elif umidade > config.UMIDADE_MAX_PERCENT and self._estado["bomba_ligada"]:
                self._estado["bomba_ligada"] = False
                self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, "desligar")
                print(f"[{self.ctrl_id}] 💧 Umidade={umidade:.1f}% > {config.UMIDADE_MAX_PERCENT}% → DESLIGAR bomba")

    def _publicar_comando(self, topico: str, acao: str) -> None:
        """Publica um comando para um atuador via MQTT."""
        payload = json.dumps({"acao": acao, "origem": self.ctrl_id, "timestamp": time.time()})
        self._mqtt_client.publish(topico, payload, qos=1)

    # ─── Callbacks MQTT ─────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(config.TOPIC_TEMPERATURA,  qos=1)
            client.subscribe(config.TOPIC_UMIDADE_SOLO, qos=1)
            print(f"[{self.ctrl_id}] Conectado ao MQTT. Assinando tópicos de sensores.")
        else:
            print(f"[{self.ctrl_id}] Falha na conexão MQTT: {reason_code}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            valor   = float(payload["valor"])
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[{self.ctrl_id}] Mensagem inválida: {e}")
            return

        with self._lock:
            if msg.topic == config.TOPIC_TEMPERATURA:
                self._estado["temperatura"] = valor
                print(f"[{self.ctrl_id}] 🌡️  Temperatura recebida: {valor:.2f}°C")
            elif msg.topic == config.TOPIC_UMIDADE_SOLO:
                self._estado["umidade_solo"] = valor
                print(f"[{self.ctrl_id}] 💧 Umidade do solo recebida: {valor:.2f}%")

            self._estado["ultima_atualizacao"] = time.time()
            self._decidir_atuacao()
            self._salvar_estado()

    # ─── Métodos XML-RPC (expostos ao middleware) ────────────────

    def obter_estado(self) -> dict:
        """
        Retorna o estado atual da estufa.
        
        Se o controlador estiver em modo byzantino, retorna dados falsificados
        para simular um nó comprometido.
        
        Returns:
            dict com temperatura, umidade_solo, bomba_ligada, exaustor_ligado,
            ultima_atualizacao, controlador_id.
        """
        with self._lock:
            if self.byzantino:
                # Retorna dados deliberadamente errados
                return {
                    "temperatura": 999.0,
                    "umidade_solo": -1.0,
                    "bomba_ligada": not self._estado.get("bomba_ligada", False),
                    "exaustor_ligado": not self._estado.get("exaustor_ligado", False),
                    "ultima_atualizacao": time.time(),
                    "controlador_id": self.ctrl_id,
                    "_byzantino": True,
                }
            return dict(self._estado)

    def comandar_bomba(self, acao: str) -> dict:
        """
        Comando manual: liga ou desliga a bomba de irrigação.
        
        Args:
            acao: 'ligar' ou 'desligar'
            
        Returns:
            dict com 'sucesso' (bool) e 'mensagem' (str).
        """
        acao = acao.lower().strip()
        if acao not in ("ligar", "desligar"):
            return {"sucesso": False, "mensagem": f"Ação inválida: '{acao}'. Use 'ligar' ou 'desligar'."}

        if self.byzantino:
            # Nó byzantino ignora o comando e retorna confirmação falsa
            return {"sucesso": True, "mensagem": f"[BYZANTINO] Bomba {acao}da (FALSO)", "byzantino": True}

        with self._lock:
            novo_estado = (acao == "ligar")
            self._estado["bomba_ligada"] = novo_estado
            self._publicar_comando(config.TOPIC_ATUADOR_BOMBA, acao)
            self._salvar_estado()
            return {"sucesso": True, "mensagem": f"Bomba {acao}da com sucesso pelo {self.ctrl_id}"}

    def comandar_exaustor(self, acao: str) -> dict:
        """
        Comando manual: liga ou desliga o exaustor.
        
        Args:
            acao: 'ligar' ou 'desligar'
            
        Returns:
            dict com 'sucesso' (bool) e 'mensagem' (str).
        """
        acao = acao.lower().strip()
        if acao not in ("ligar", "desligar"):
            return {"sucesso": False, "mensagem": f"Ação inválida: '{acao}'. Use 'ligar' ou 'desligar'."}

        if self.byzantino:
            return {"sucesso": True, "mensagem": f"[BYZANTINO] Exaustor {acao}do (FALSO)", "byzantino": True}

        with self._lock:
            novo_estado = (acao == "ligar")
            self._estado["exaustor_ligado"] = novo_estado
            self._publicar_comando(config.TOPIC_ATUADOR_EXAUSTOR, acao)
            self._salvar_estado()
            return {"sucesso": True, "mensagem": f"Exaustor {acao}do com sucesso pelo {self.ctrl_id}"}

    def ping(self) -> str:
        """Health-check usado pelo middleware para detectar réplicas vivas."""
        return f"pong:{self.ctrl_id}"

    # ─── Inicialização ───────────────────────────────────────────

    def iniciar(self, host: str, port: int) -> None:
        """
        Inicia o controlador:
          1. Conecta ao broker MQTT e começa a consumir mensagens dos sensores.
          2. Sobe o servidor XML-RPC na porta especificada.
        """
        # Thread MQTT (não bloqueante)
        self._mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"controlador_{self.ctrl_id}"
        )
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_message
        self._mqtt_client.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_KEEPALIVE)
        self._mqtt_client.loop_start()

        # Servidor XML-RPC (bloqueante — deve ser a última chamada)
        class SilentHandler(SimpleXMLRPCRequestHandler):
            """Suprime logs HTTP do servidor XML-RPC."""
            def log_message(self, fmt, *args):
                pass

        server = SimpleXMLRPCServer(
            (host, port),
            requestHandler=SilentHandler,
            allow_none=True,
            logRequests=False,
        )
        server.register_instance(self)
        server.register_introspection_functions()

        modo = " [MODO BYZANTINO]" if self.byzantino else ""
        print(f"[{self.ctrl_id}] XML-RPC server iniciado em {host}:{port}{modo}")
        server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Controlador da Estufa")
    parser.add_argument("--id",       required=True,  help="ID do controlador (ex: ctrl_1)")
    parser.add_argument("--port",     required=True,  type=int, help="Porta XML-RPC")
    parser.add_argument("--data",     required=True,  help="Arquivo JSON de persistência")
    parser.add_argument("--host",     default="localhost", help="Host do servidor XML-RPC")
    parser.add_argument("--byzantino", action="store_true", help="Modo byzantino (retorna dados falsos)")
    args = parser.parse_args()

    ctrl = Controlador(ctrl_id=args.id, data_file=args.data, byzantino=args.byzantino)
    ctrl.iniciar(host=args.host, port=args.port)
```

---

## Fase 5 — Middleware (Votação Majoritária e BFT)

**Agente responsável:** Fase 5  
**Pré-requisito:** Fase 4 concluída

O middleware é a peça central que resolve os dois desafios técnicos obrigatórios:
- **Tolerância à queda**: se 1 de 3 controladores cair, o sistema continua (com 2 respostas)
- **Tolerância Byzantina**: se 1 controlador responder valor discrepante, a maioria prevalece

### 5.1 — Arquivo `estufa/middleware.py`

Criar `trabalho_pratico1/estufa/middleware.py` com o conteúdo **exato**:

```python
"""
middleware.py — Middleware de Invocação Distribuída com Votação Majoritária.

Atua como camada de abstração entre o Cliente e o cluster de 3 Controladores.

Algoritmo de votação (Byzantine Fault Tolerance simplificado):
  - Envia a chamada XML-RPC para TODOS os controladores em paralelo.
  - Coleta respostas dentro do timeout configurado.
  - Se receber >= QUORUM_MINIMO (2) respostas concordantes, retorna a resposta majoritária.
  - Se não atingir quorum, lança exceção informando ao cliente.

Tolerância a falhas modelada:
  1. Queda de controlador: timeout na chamada → controlador ignorado.
  2. Controlador byzantino: resposta discrepante → descartada por não atingir quorum.
"""

import concurrent.futures
import collections
import json
import xmlrpc.client
from typing import Any, Optional
from estufa import config


class ErroQuorum(Exception):
    """Levantada quando não é possível atingir quorum de respostas concordantes."""
    pass


class Middleware:
    """
    Middleware de invocação distribuída para o cluster de controladores.

    Uso:
        mw = Middleware()
        estado = mw.obter_estado()          # leitura com votação
        mw.comandar_bomba('ligar')          # escrita com votação
    """

    def __init__(self, controladores: list = None, timeout: int = None):
        """
        Args:
            controladores: Lista de dicts com 'host', 'port', 'id'.
                           Se None, usa config.CONTROLADORES.
            timeout: Timeout por chamada XML-RPC em segundos.
                     Se None, usa config.TIMEOUT_RPC_SEGUNDOS.
        """
        self._controladores = controladores or config.CONTROLADORES
        self._timeout = timeout or config.TIMEOUT_RPC_SEGUNDOS

    def _criar_proxy(self, controlador: dict) -> xmlrpc.client.ServerProxy:
        """Cria um proxy XML-RPC para o controlador especificado."""
        url = f"http://{controlador['host']}:{controlador['port']}"
        return xmlrpc.client.ServerProxy(url, allow_none=True)

    def _chamar_controlador(self, controlador: dict, metodo: str, *args) -> Any:
        """
        Realiza uma única chamada XML-RPC a um controlador.

        Returns:
            Resultado da chamada.

        Raises:
            Exception: qualquer falha de rede, timeout ou erro do servidor.
        """
        proxy = self._criar_proxy(controlador)
        func = getattr(proxy, metodo)
        return func(*args)

    def _votar(self, metodo: str, *args) -> Any:
        """
        Núcleo do algoritmo de votação por maioria.

        Envia a chamada para todos os controladores em paralelo (ThreadPoolExecutor),
        aguarda até o timeout e verifica se há quorum de respostas concordantes.

        Para comparação de dicts (estado), serializa para JSON com chaves ordenadas.
        Para strings simples, compara diretamente.

        Returns:
            Resultado majoritário.

        Raises:
            ErroQuorum: se não houver respostas suficientes ou concordantes.
        """
        resultados = []
        erros      = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self._controladores)) as executor:
            futures = {
                executor.submit(self._chamar_controlador, ctrl, metodo, *args): ctrl
                for ctrl in self._controladores
            }
            for future in concurrent.futures.as_completed(futures, timeout=self._timeout + 1):
                ctrl = futures[future]
                try:
                    resultado = future.result(timeout=self._timeout)
                    resultados.append((ctrl["id"], resultado))
                except Exception as e:
                    erros.append((ctrl["id"], str(e)))
                    print(f"[MIDDLEWARE] ⚠️  Controlador {ctrl['id']} falhou: {e}")

        if not resultados:
            raise ErroQuorum(
                f"Nenhuma resposta recebida de {len(self._controladores)} controladores. "
                f"Erros: {erros}"
            )

        # ── Votação ──────────────────────────────────────────────────────────
        # Serializa cada resultado para string comparável
        def _normalizar(valor: Any) -> str:
            if isinstance(valor, dict):
                # Remove campos que não devem influenciar a comparação
                copia = {k: v for k, v in valor.items()
                         if k not in ("ultima_atualizacao", "controlador_id", "_byzantino")}
                return json.dumps(copia, sort_keys=True)
            return str(valor)

        contagem = collections.Counter(_normalizar(r) for _, r in resultados)
        mais_comum, votos = contagem.most_common(1)[0]

        print(f"[MIDDLEWARE] Votos recebidos: {dict(contagem)} | Quorum mínimo: {config.QUORUM_MINIMO}")

        if votos < config.QUORUM_MINIMO:
            raise ErroQuorum(
                f"Quorum não atingido: {votos} voto(s) para a resposta mais comum "
                f"(mínimo: {config.QUORUM_MINIMO}). Respostas: {resultados}"
            )

        # Retorna o resultado original (não a string normalizada)
        for _, resultado in resultados:
            if _normalizar(resultado) == mais_comum:
                return resultado

    # ─── API Pública ────────────────────────────────────────────────────────

    def obter_estado(self) -> dict:
        """
        Consulta o estado atual da estufa via votação majoritária.

        Returns:
            dict com o estado consensual da estufa.

        Raises:
            ErroQuorum: se não houver consenso suficiente.
        """
        return self._votar("obter_estado")

    def comandar_bomba(self, acao: str) -> dict:
        """
        Envia comando de ligar/desligar a bomba para todos os controladores.

        A confirmação é válida se >= QUORUM_MINIMO controladores confirmarem
        sucesso. Em caso de nó byzantino, a maioria saudável prevalece.

        Args:
            acao: 'ligar' ou 'desligar'

        Returns:
            dict de resposta consensual.

        Raises:
            ErroQuorum: se não houver confirmação suficiente.
        """
        return self._votar("comandar_bomba", acao)

    def comandar_exaustor(self, acao: str) -> dict:
        """
        Envia comando de ligar/desligar o exaustor para todos os controladores.

        Args:
            acao: 'ligar' ou 'desligar'

        Returns:
            dict de resposta consensual.

        Raises:
            ErroQuorum: se não houver confirmação suficiente.
        """
        return self._votar("comandar_exaustor", acao)

    def verificar_saude(self) -> dict:
        """
        Verifica quais controladores estão respondendo (health-check).

        Returns:
            dict mapeando controlador_id → 'ok' ou mensagem de erro.
        """
        saude = {}
        for ctrl in self._controladores:
            try:
                proxy = self._criar_proxy(ctrl)
                resp  = proxy.ping()
                saude[ctrl["id"]] = "ok" if "pong" in str(resp) else f"resposta inesperada: {resp}"
            except Exception as e:
                saude[ctrl["id"]] = f"OFFLINE: {e}"
        return saude
```

---

## Fase 6 — Cliente (Interface do Usuário)

**Agente responsável:** Fase 6  
**Pré-requisito:** Fase 5 concluída

### 6.1 — Arquivo `estufa/cliente.py`

Criar `trabalho_pratico1/estufa/cliente.py` com o conteúdo **exato**:

```python
"""
cliente.py — Interface de linha de comando para o sistema Estufa Agrícola.

O cliente interage com o cluster de controladores EXCLUSIVAMENTE através
do Middleware, que gerencia votação e tolerância a falhas transparentemente.

Uso:
    python -m estufa.cliente
    python -m estufa.cliente --auto   # Modo automático: consulta e exibe estado a cada 3s
"""

import argparse
import time
from estufa.middleware import Middleware, ErroQuorum


def exibir_estado(estado: dict) -> None:
    """Formata e exibe o estado atual da estufa."""
    print("\n" + "═" * 50)
    print("         🌿 ESTADO ATUAL DA ESTUFA 🌿")
    print("═" * 50)

    temp    = estado.get("temperatura")
    umidade = estado.get("umidade_solo")
    bomba   = estado.get("bomba_ligada")
    exaustor = estado.get("exaustor_ligado")

    print(f"  🌡️  Temperatura:   {f'{temp:.2f}°C' if temp is not None else 'N/A'}")
    print(f"  💧 Umidade solo:  {f'{umidade:.2f}%' if umidade is not None else 'N/A'}")
    print(f"  🚿 Bomba:         {'🟢 LIGADA' if bomba else '🔴 DESLIGADA'}")
    print(f"  💨 Exaustor:      {'🟢 LIGADO' if exaustor else '🔴 DESLIGADO'}")
    print("═" * 50 + "\n")


def menu_interativo(mw: Middleware) -> None:
    """Loop principal do menu interativo."""
    while True:
        print("\n📋 MENU — Estufa Agrícola Distribuída")
        print("  1. Consultar estado atual")
        print("  2. Ligar bomba de irrigação")
        print("  3. Desligar bomba de irrigação")
        print("  4. Ligar exaustor")
        print("  5. Desligar exaustor")
        print("  6. Verificar saúde dos controladores")
        print("  0. Sair")

        escolha = input("\n▶ Escolha: ").strip()

        try:
            if escolha == "1":
                estado = mw.obter_estado()
                exibir_estado(estado)

            elif escolha == "2":
                resp = mw.comandar_bomba("ligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "3":
                resp = mw.comandar_bomba("desligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "4":
                resp = mw.comandar_exaustor("ligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "5":
                resp = mw.comandar_exaustor("desligar")
                print(f"✅ {resp.get('mensagem', resp)}")

            elif escolha == "6":
                saude = mw.verificar_saude()
                print("\n🏥 Saúde dos Controladores:")
                for ctrl_id, status in saude.items():
                    icone = "🟢" if status == "ok" else "🔴"
                    print(f"  {icone} {ctrl_id}: {status}")

            elif escolha == "0":
                print("👋 Encerrando cliente.")
                break

            else:
                print("⚠️  Opção inválida.")

        except ErroQuorum as e:
            print(f"\n❌ ERRO DE QUORUM: {e}")
            print("   O sistema não conseguiu atingir consenso.")
            print("   Verifique se os controladores estão em execução.")


def modo_automatico(mw: Middleware, intervalo: float = 3.0) -> None:
    """Exibe o estado da estufa em loop automático."""
    print(f"🤖 Modo automático: consultando a cada {intervalo}s. Ctrl+C para parar.")
    try:
        while True:
            try:
                estado = mw.obter_estado()
                exibir_estado(estado)
            except ErroQuorum as e:
                print(f"❌ ERRO DE QUORUM: {e}")
            time.sleep(intervalo)
    except KeyboardInterrupt:
        print("\n👋 Encerrando.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente — Estufa Agrícola Distribuída")
    parser.add_argument("--auto", action="store_true", help="Modo automático (polling)")
    parser.add_argument("--intervalo", type=float, default=3.0,
                        help="Intervalo do modo automático (segundos)")
    args = parser.parse_args()

    mw = Middleware()

    if args.auto:
        modo_automatico(mw, intervalo=args.intervalo)
    else:
        menu_interativo(mw)
```

---

## Fase 7 — Testes Automatizados

**Agente responsável:** Fase 7  
**Pré-requisito:** Fases 4 e 5 concluídas

Os testes são **completamente autocontidos**: não dependem de broker MQTT externo.
Os controladores nos testes são iniciados em threads (sem MQTT) para isolar a lógica XML-RPC.

### 7.1 — Arquivo `tests/test_controlador.py`

Criar `trabalho_pratico1/tests/test_controlador.py` com o conteúdo **exato**:

```python
"""
test_controlador.py — Testes unitários do Controlador.

Testa:
  - Lógica de decisão (thresholds)
  - Persistência JSON (leitura/escrita)
  - Métodos XML-RPC (obter_estado, comandar_bomba, comandar_exaustor, ping)
  - Modo byzantino
"""

import json
import os
import tempfile
import threading
import time
import xmlrpc.client
import pytest
from estufa.controlador import Controlador
from estufa import config


# ─────────────────────────────────────────
# Fixture: controlador sem MQTT (unit test)
# ─────────────────────────────────────────

@pytest.fixture
def ctrl_sem_mqtt(tmp_path):
    """
    Cria um Controlador sem iniciar o MQTT (apenas para testar a lógica interna).
    O arquivo de dados é criado em um diretório temporário.
    """
    data_file = str(tmp_path / "test_estado.json")
    ctrl = Controlador(ctrl_id="ctrl_test", data_file=data_file)
    # Injeta um cliente MQTT falso para que _publicar_comando não quebre
    ctrl._mqtt_client = _MqttFake()
    return ctrl


class _MqttFake:
    """Mock mínimo do cliente MQTT para testes sem broker."""
    def publish(self, topic, payload, qos=0):
        pass  # Descarta a publicação


# ─────────────────────────────────────────
# Testes: Lógica de Decisão
# ─────────────────────────────────────────

class TestLogicaDecisao:
    def test_bomba_liga_quando_umidade_baixa(self, ctrl_sem_mqtt):
        ctrl = ctrl_sem_mqtt
        ctrl._estado["umidade_solo"] = config.UMIDADE_MIN_PERCENT - 1  # abaixo do mínimo
        ctrl._estado["temperatura"]  = 25.0
        ctrl._decidir_atuacao()
        assert ctrl._estado["bomba_ligada"] is True

    def test_bomba_desliga_quando_umidade_alta(self, ctrl_sem_mqtt):
        ctrl = ctrl_sem_mqtt
        ctrl._estado["umidade_solo"] = config.UMIDADE_MAX_PERCENT + 1  # acima do máximo
        ctrl._estado["bomba_ligada"] = True
        ctrl._decidir_atuacao()
        assert ctrl._estado["bomba_ligada"] is False

    def test_bomba_nao_muda_em_umidade_normal(self, ctrl_sem_mqtt):
        ctrl = ctrl_sem_mqtt
        ctrl._estado["umidade_solo"] = 50.0  # dentro do range normal
        ctrl._estado["bomba_ligada"] = False
        ctrl._decidir_atuacao()
        assert ctrl._estado["bomba_ligada"] is False

    def test_exaustor_liga_quando_temp_alta(self, ctrl_sem_mqtt):
        ctrl = ctrl_sem_mqtt
        ctrl._estado["temperatura"]  = config.TEMP_MAX_CELSIUS + 1  # acima do máximo
        ctrl._estado["umidade_solo"] = 50.0
        ctrl._decidir_atuacao()
        assert ctrl._estado["exaustor_ligado"] is True

    def test_exaustor_desliga_quando_temp_baixa(self, ctrl_sem_mqtt):
        ctrl = ctrl_sem_mqtt
        ctrl._estado["temperatura"]     = config.TEMP_MIN_CELSIUS - 1  # abaixo do mínimo
        ctrl._estado["exaustor_ligado"] = True
        ctrl._decidir_atuacao()
        assert ctrl._estado["exaustor_ligado"] is False

    def test_exaustor_nao_muda_em_temp_normal(self, ctrl_sem_mqtt):
        ctrl = ctrl_sem_mqtt
        ctrl._estado["temperatura"]     = 25.0  # temperatura normal
        ctrl._estado["exaustor_ligado"] = False
        ctrl._decidir_atuacao()
        assert ctrl._estado["exaustor_ligado"] is False


# ─────────────────────────────────────────
# Testes: Persistência JSON
# ─────────────────────────────────────────

class TestPersistencia:
    def test_salvar_e_carregar_estado(self, tmp_path):
        data_file = str(tmp_path / "estado.json")
        ctrl = Controlador(ctrl_id="ctrl_p", data_file=data_file)
        ctrl._mqtt_client = _MqttFake()

        ctrl._estado["temperatura"]  = 28.5
        ctrl._estado["umidade_solo"] = 45.0
        ctrl._salvar_estado()

        # Novo controlador carrega do mesmo arquivo
        ctrl2 = Controlador(ctrl_id="ctrl_p2", data_file=data_file)
        assert ctrl2._estado["temperatura"]  == 28.5
        assert ctrl2._estado["umidade_solo"] == 45.0

    def test_estado_inicial_sem_arquivo(self, tmp_path):
        data_file = str(tmp_path / "nao_existe.json")
        ctrl = Controlador(ctrl_id="ctrl_ini", data_file=data_file)
        assert ctrl._estado["temperatura"]   is None
        assert ctrl._estado["umidade_solo"]  is None
        assert ctrl._estado["bomba_ligada"]  is False
        assert ctrl._estado["exaustor_ligado"] is False

    def test_arquivo_corrompido_usa_estado_inicial(self, tmp_path):
        data_file = str(tmp_path / "corrompido.json")
        with open(data_file, "w") as f:
            f.write("INVALIDO_JSON{{{{")
        ctrl = Controlador(ctrl_id="ctrl_corr", data_file=data_file)
        assert ctrl._estado["temperatura"] is None


# ─────────────────────────────────────────
# Fixture: controlador com servidor XML-RPC
# ─────────────────────────────────────────

def _iniciar_servidor_xmlrpc(ctrl: Controlador, host: str, port: int) -> threading.Thread:
    """
    Inicia o servidor XML-RPC do controlador em uma thread daemon.
    Aguarda até o servidor estar pronto.
    """
    from xmlrpc.server import SimpleXMLRPCServer

    server = SimpleXMLRPCServer(
        (host, port),
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(ctrl)
    server.register_introspection_functions()
    server._BaseServer__shutdown_request = False  # necessário para shutdown thread-safe

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.server = server
    t.start()
    time.sleep(0.1)  # aguarda o servidor estar pronto
    return t


@pytest.fixture
def servidor_xmlrpc(tmp_path):
    """
    Inicia um controlador com servidor XML-RPC em porta de teste (9901).
    Retorna tupla (controlador, proxy_xmlrpc).
    """
    PORT = 9901
    data_file = str(tmp_path / "ctrl_xmlrpc.json")
    ctrl = Controlador(ctrl_id="ctrl_rpc", data_file=data_file)
    ctrl._mqtt_client = _MqttFake()

    _iniciar_servidor_xmlrpc(ctrl, "localhost", PORT)

    proxy = xmlrpc.client.ServerProxy(f"http://localhost:{PORT}", allow_none=True)
    return ctrl, proxy


@pytest.fixture
def servidor_xmlrpc_byzantino(tmp_path):
    """
    Inicia um controlador BYZANTINO com servidor XML-RPC em porta de teste (9902).
    """
    PORT = 9902
    data_file = str(tmp_path / "ctrl_byz.json")
    ctrl = Controlador(ctrl_id="ctrl_byz", data_file=data_file, byzantino=True)
    ctrl._mqtt_client = _MqttFake()

    _iniciar_servidor_xmlrpc(ctrl, "localhost", PORT)

    proxy = xmlrpc.client.ServerProxy(f"http://localhost:{PORT}", allow_none=True)
    return ctrl, proxy


# ─────────────────────────────────────────
# Testes: Métodos XML-RPC
# ─────────────────────────────────────────

class TestMetodosXMLRPC:
    def test_ping(self, servidor_xmlrpc):
        _, proxy = servidor_xmlrpc
        resp = proxy.ping()
        assert "pong" in resp

    def test_obter_estado_retorna_dict(self, servidor_xmlrpc):
        _, proxy = servidor_xmlrpc
        estado = proxy.obter_estado()
        assert "temperatura" in estado
        assert "umidade_solo" in estado
        assert "bomba_ligada" in estado
        assert "exaustor_ligado" in estado

    def test_comandar_bomba_ligar(self, servidor_xmlrpc):
        _, proxy = servidor_xmlrpc
        resp = proxy.comandar_bomba("ligar")
        assert resp["sucesso"] is True
        estado = proxy.obter_estado()
        assert estado["bomba_ligada"] is True

    def test_comandar_bomba_desligar(self, servidor_xmlrpc):
        _, proxy = servidor_xmlrpc
        proxy.comandar_bomba("ligar")  # liga primeiro
        resp = proxy.comandar_bomba("desligar")
        assert resp["sucesso"] is True
        estado = proxy.obter_estado()
        assert estado["bomba_ligada"] is False

    def test_comandar_exaustor_ligar(self, servidor_xmlrpc):
        _, proxy = servidor_xmlrpc
        resp = proxy.comandar_exaustor("ligar")
        assert resp["sucesso"] is True
        estado = proxy.obter_estado()
        assert estado["exaustor_ligado"] is True

    def test_comandar_bomba_acao_invalida(self, servidor_xmlrpc):
        _, proxy = servidor_xmlrpc
        resp = proxy.comandar_bomba("invalidar")
        assert resp["sucesso"] is False
        assert "Ação inválida" in resp["mensagem"]


# ─────────────────────────────────────────
# Testes: Modo Byzantino
# ─────────────────────────────────────────

class TestModoByzantino:
    def test_estado_byzantino_tem_valores_falsos(self, servidor_xmlrpc_byzantino):
        _, proxy = servidor_xmlrpc_byzantino
        estado = proxy.obter_estado()
        # O nó byzantino retorna temperatura 999 e umidade -1
        assert estado["temperatura"] == 999.0
        assert estado["umidade_solo"] == -1.0

    def test_comando_byzantino_retorna_falso_sucesso(self, servidor_xmlrpc_byzantino):
        _, proxy = servidor_xmlrpc_byzantino
        resp = proxy.comandar_bomba("ligar")
        # O nó byzantino retorna "sucesso" mas o flag byzantino está presente
        assert resp.get("byzantino") is True
```

### 7.2 — Arquivo `tests/test_middleware.py`

Criar `trabalho_pratico1/tests/test_middleware.py` com o conteúdo **exato**:

```python
"""
test_middleware.py — Testes do Middleware com votação majoritária.

Cenários testados:
  1. Votação normal (3 de 3 concordam)
  2. Queda de 1 controlador (2 de 3 disponíveis — quorum atingido)
  3. Controlador byzantino (2 normais vs 1 mentindo — maioria prevalece)
  4. Queda de 2 controladores (1 de 3 — quorum NÃO atingido → ErroQuorum)
  5. Votação todos byzantinos (sem consenso → ErroQuorum)
  6. Comandos com queda de 1 controlador
"""

import threading
import time
import pytest
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCServer
from estufa.middleware import Middleware, ErroQuorum
from estufa import config


# ─────────────────────────────────────────
# Servidores XML-RPC falsos para testes de middleware
# ─────────────────────────────────────────

class _ControladorFake:
    """
    Servidor XML-RPC fake para testes de middleware.
    Retorna dados configuráveis para simular diferentes cenários.
    """

    def __init__(self, ctrl_id: str, estado_fixo: dict = None, byzantino: bool = False):
        self.ctrl_id = ctrl_id
        self.byzantino = byzantino
        self._estado = estado_fixo or {
            "temperatura": 25.0,
            "umidade_solo": 50.0,
            "bomba_ligada": False,
            "exaustor_ligado": False,
            "ultima_atualizacao": 0,
            "controlador_id": ctrl_id,
        }

    def obter_estado(self):
        if self.byzantino:
            return {**self._estado, "temperatura": 999.0, "umidade_solo": -1.0, "_byzantino": True}
        return dict(self._estado)

    def comandar_bomba(self, acao):
        if self.byzantino:
            return {"sucesso": True, "mensagem": "FALSO", "byzantino": True}
        self._estado["bomba_ligada"] = (acao == "ligar")
        return {"sucesso": True, "mensagem": f"Bomba {acao}da"}

    def comandar_exaustor(self, acao):
        if self.byzantino:
            return {"sucesso": True, "mensagem": "FALSO", "byzantino": True}
        self._estado["exaustor_ligado"] = (acao == "ligar")
        return {"sucesso": True, "mensagem": f"Exaustor {acao}do"}

    def ping(self):
        return f"pong:{self.ctrl_id}"


def _subir_fake_server(fake: _ControladorFake, port: int) -> SimpleXMLRPCServer:
    """Sobe um servidor XML-RPC fake em uma thread daemon."""
    server = SimpleXMLRPCServer(("localhost", port), allow_none=True, logRequests=False)
    server.register_instance(fake)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)
    return server


# ─────────────────────────────────────────
# Fixture de cluster de 3 controladores fake
# ─────────────────────────────────────────

# Portas para os testes de middleware (diferentes das do test_controlador)
_PORTAS_MW = [9801, 9802, 9803]
_CONTROLADORES_MW = [
    {"id": f"ctrl_{i+1}", "host": "localhost", "port": _PORTAS_MW[i]}
    for i in range(3)
]


@pytest.fixture(scope="module")
def cluster_normal():
    """Cluster de 3 controladores normais (todos concordam)."""
    fakes = [_ControladorFake(f"ctrl_{i+1}") for i in range(3)]
    servers = [_subir_fake_server(fakes[i], _PORTAS_MW[i]) for i in range(3)]
    mw = Middleware(controladores=_CONTROLADORES_MW, timeout=2)
    yield mw, fakes, servers


class TestVotacaoNormal:
    def test_obter_estado_retorna_consenso(self, cluster_normal):
        mw, fakes, _ = cluster_normal
        estado = mw.obter_estado()
        assert estado["temperatura"] == 25.0
        assert estado["umidade_solo"] == 50.0
        assert estado["bomba_ligada"] is False

    def test_comandar_bomba_ligar(self, cluster_normal):
        mw, fakes, _ = cluster_normal
        resp = mw.comandar_bomba("ligar")
        assert resp["sucesso"] is True
        # Todos os 3 fakes devem ter sido atualizados
        for fake in fakes:
            assert fake._estado["bomba_ligada"] is True

    def test_verificar_saude_todos_ok(self, cluster_normal):
        mw, _, _ = cluster_normal
        saude = mw.verificar_saude()
        assert all(v == "ok" for v in saude.values())


# ─────────────────────────────────────────
# Testes: 1 controlador offline (queda)
# ─────────────────────────────────────────

# Porta diferente que não tem servidor
_PORTAS_COM_QUEDA = [9811, 9812, 9999]  # 9999 não tem servidor
_CTRL_COM_QUEDA = [
    {"id": "ctrl_1", "host": "localhost", "port": 9811},
    {"id": "ctrl_2", "host": "localhost", "port": 9812},
    {"id": "ctrl_3", "host": "localhost", "port": 9999},  # OFFLINE
]


@pytest.fixture(scope="module")
def cluster_com_queda():
    """2 controladores normais + 1 offline (porta sem servidor)."""
    fakes = [_ControladorFake("ctrl_1"), _ControladorFake("ctrl_2")]
    servers = [
        _subir_fake_server(fakes[0], 9811),
        _subir_fake_server(fakes[1], 9812),
    ]
    mw = Middleware(controladores=_CTRL_COM_QUEDA, timeout=1)
    yield mw, fakes, servers


class TestQuedaDeControlador:
    def test_obter_estado_com_1_offline(self, cluster_com_queda):
        """Com 1 controlador offline, os 2 restantes formam quorum."""
        mw, _, _ = cluster_com_queda
        estado = mw.obter_estado()
        assert estado["temperatura"] == 25.0  # quorum atingido com 2/3

    def test_comandar_bomba_com_1_offline(self, cluster_com_queda):
        """Comando deve ser aceito mesmo com 1 controlador offline."""
        mw, _, _ = cluster_com_queda
        resp = mw.comandar_bomba("ligar")
        assert resp["sucesso"] is True


# ─────────────────────────────────────────
# Testes: Controlador Byzantino (mentindo)
# ─────────────────────────────────────────

_PORTAS_BYZ = [9821, 9822, 9823]
_CTRL_BYZ = [
    {"id": "ctrl_1", "host": "localhost", "port": 9821},
    {"id": "ctrl_2", "host": "localhost", "port": 9822},
    {"id": "ctrl_byz", "host": "localhost", "port": 9823},
]


@pytest.fixture(scope="module")
def cluster_byzantino():
    """2 controladores normais + 1 byzantino."""
    fakes = [
        _ControladorFake("ctrl_1"),
        _ControladorFake("ctrl_2"),
        _ControladorFake("ctrl_byz", byzantino=True),
    ]
    servers = [_subir_fake_server(fakes[i], _PORTAS_BYZ[i]) for i in range(3)]
    mw = Middleware(controladores=_CTRL_BYZ, timeout=2)
    yield mw, fakes, servers


class TestByzantineFaultTolerance:
    def test_maioria_prevalece_sobre_byzantino(self, cluster_byzantino):
        """
        Com 2 controladores normais e 1 byzantino (temperatura=999),
        o middleware deve retornar a resposta da maioria (temperatura=25).
        """
        mw, _, _ = cluster_byzantino
        estado = mw.obter_estado()
        # A maioria diz temperatura=25, não 999
        assert estado["temperatura"] == 25.0
        assert estado["umidade_solo"] == 50.0

    def test_comando_maioria_prevalece(self, cluster_byzantino):
        """Comando é aceito quando 2 de 3 confirmam com sucesso."""
        mw, _, _ = cluster_byzantino
        resp = mw.comandar_bomba("ligar")
        assert resp["sucesso"] is True
        assert resp.get("byzantino") is not True  # resposta é da maioria honesta


# ─────────────────────────────────────────
# Testes: Sem Quorum (2 offline)
# ─────────────────────────────────────────

_CTRL_SEM_QUORUM = [
    {"id": "ctrl_1", "host": "localhost", "port": 9991},  # OFFLINE
    {"id": "ctrl_2", "host": "localhost", "port": 9992},  # OFFLINE
    {"id": "ctrl_3", "host": "localhost", "port": 9993},  # OFFLINE
]


class TestSemQuorum:
    def test_erro_quorum_quando_todos_offline(self):
        """Com todos os controladores offline, deve levantar ErroQuorum."""
        mw = Middleware(controladores=_CTRL_SEM_QUORUM, timeout=1)
        with pytest.raises(ErroQuorum):
            mw.obter_estado()

    def test_erro_quorum_quando_2_offline(self):
        """Com 2 de 3 offline, quorum não é atingido (1 < 2 mínimo)."""
        # Apenas ctrl_3 no ar (porta 9831)
        fake = _ControladorFake("ctrl_solo")
        _subir_fake_server(fake, 9831)
        ctrl_parcial = [
            {"id": "ctrl_1", "host": "localhost", "port": 9991},  # OFFLINE
            {"id": "ctrl_2", "host": "localhost", "port": 9992},  # OFFLINE
            {"id": "ctrl_3", "host": "localhost", "port": 9831},  # único online
        ]
        mw = Middleware(controladores=ctrl_parcial, timeout=1)
        with pytest.raises(ErroQuorum):
            mw.obter_estado()
```

### 7.3 — Arquivo `tests/test_integracao.py`

Criar `trabalho_pratico1/tests/test_integracao.py` com o conteúdo **exato**:

```python
"""
test_integracao.py — Testes de integração com broker MQTT real (Docker).

ATENÇÃO: estes testes requerem o broker Mosquitto em execução:
    docker compose up -d

Se o broker não estiver disponível, os testes são pulados automaticamente
via pytest.mark.skipif.

Testa o fluxo completo:
  Sensor → MQTT → Controlador → decisão de atuação → estado atualizado
"""

import json
import threading
import time
import pytest
import paho.mqtt.client as mqtt
from estufa import config
from estufa.controlador import Controlador


def _broker_disponivel() -> bool:
    """Verifica se o broker MQTT está acessível."""
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_check")
        client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=5)
        client.disconnect()
        return True
    except Exception:
        return False


broker_disponivel = pytest.mark.skipif(
    not _broker_disponivel(),
    reason="Broker MQTT não disponível. Execute: docker compose up -d"
)


class _MqttFake:
    """Mock de cliente MQTT para testes sem broker."""
    publicacoes = []
    def publish(self, topic, payload, qos=0):
        _MqttFake.publicacoes.append((topic, payload))


@pytest.fixture
def ctrl_com_mqtt_fake(tmp_path):
    """Controlador com cliente MQTT fake (sem broker real)."""
    data_file = str(tmp_path / "ctrl_integ.json")
    ctrl = Controlador(ctrl_id="ctrl_integ", data_file=data_file)
    ctrl._mqtt_client = _MqttFake()
    return ctrl


class TestDecisaoComDadosSensorSimulados:
    """
    Testa o fluxo de decisão simulando a chegada de mensagens MQTT
    sem precisar de um broker real.
    """

    def _simular_mensagem_mqtt(self, ctrl: Controlador, topico: str, valor: float):
        """Simula a chegada de uma mensagem MQTT chamando o handler diretamente."""
        payload_bytes = json.dumps({"valor": valor, "unidade": "", "timestamp": time.time()}).encode()

        class MsgFake:
            topic = topico
            payload = payload_bytes

        ctrl._on_message(client=None, userdata=None, msg=MsgFake())

    def test_sensor_seco_dispara_bomba(self, ctrl_com_mqtt_fake):
        ctrl = ctrl_com_mqtt_fake
        # Umidade abaixo do mínimo → deve ligar a bomba
        self._simular_mensagem_mqtt(ctrl, config.TOPIC_UMIDADE_SOLO, config.UMIDADE_MIN_PERCENT - 5)
        assert ctrl._estado["bomba_ligada"] is True

    def test_sensor_umido_desliga_bomba(self, ctrl_com_mqtt_fake):
        ctrl = ctrl_com_mqtt_fake
        ctrl._estado["bomba_ligada"] = True
        # Umidade acima do máximo → deve desligar a bomba
        self._simular_mensagem_mqtt(ctrl, config.TOPIC_UMIDADE_SOLO, config.UMIDADE_MAX_PERCENT + 5)
        assert ctrl._estado["bomba_ligada"] is False

    def test_temperatura_alta_dispara_exaustor(self, ctrl_com_mqtt_fake):
        ctrl = ctrl_com_mqtt_fake
        # Temperatura acima do máximo → deve ligar o exaustor
        self._simular_mensagem_mqtt(ctrl, config.TOPIC_TEMPERATURA, config.TEMP_MAX_CELSIUS + 5)
        assert ctrl._estado["exaustor_ligado"] is True

    def test_mensagem_invalida_nao_quebra_controlador(self, ctrl_com_mqtt_fake):
        """Mensagem com payload inválido não deve lançar exceção."""
        ctrl = ctrl_com_mqtt_fake

        class MsgInvalida:
            topic = config.TOPIC_TEMPERATURA
            payload = b"INVALIDO"

        ctrl._on_message(client=None, userdata=None, msg=MsgInvalida())
        # Nenhuma exceção — estado deve permanecer None
        assert ctrl._estado["temperatura"] is None

    def test_estado_salvo_apos_leitura_sensor(self, ctrl_com_mqtt_fake, tmp_path):
        ctrl = ctrl_com_mqtt_fake
        self._simular_mensagem_mqtt(ctrl, config.TOPIC_TEMPERATURA, 30.0)
        # O estado deve ter sido salvo no arquivo JSON
        assert os.path.exists(ctrl.data_file)
        with open(ctrl.data_file, "r") as f:
            salvo = json.load(f)
        assert salvo["temperatura"] == 30.0


@broker_disponivel
class TestIntegracaoComBrokerReal:
    """
    Testes de integração que requerem o broker Mosquitto em execução.
    Execute: docker compose up -d
    """

    def test_publicar_e_receber_temperatura(self):
        """Publica temperatura e verifica recebimento via MQTT."""
        recebido = []

        def on_message(client, userdata, msg):
            recebido.append(json.loads(msg.payload.decode()))

        # Subscriber
        sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_sub_temp")
        sub.on_message = on_message
        sub.connect(config.MQTT_HOST, config.MQTT_PORT)
        sub.subscribe(config.TOPIC_TEMPERATURA, qos=1)
        sub.loop_start()
        time.sleep(0.1)

        # Publisher
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_pub_temp")
        pub.connect(config.MQTT_HOST, config.MQTT_PORT)
        payload = json.dumps({"valor": 28.5, "unidade": "°C", "timestamp": time.time()})
        pub.publish(config.TOPIC_TEMPERATURA, payload, qos=1)
        pub.disconnect()

        time.sleep(0.5)
        sub.loop_stop()
        sub.disconnect()

        assert len(recebido) >= 1
        assert recebido[0]["valor"] == 28.5

    def test_publicar_e_receber_umidade(self):
        """Publica umidade e verifica recebimento via MQTT."""
        recebido = []

        def on_message(client, userdata, msg):
            recebido.append(json.loads(msg.payload.decode()))

        sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_sub_umid")
        sub.on_message = on_message
        sub.connect(config.MQTT_HOST, config.MQTT_PORT)
        sub.subscribe(config.TOPIC_UMIDADE_SOLO, qos=1)
        sub.loop_start()
        time.sleep(0.1)

        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_pub_umid")
        pub.connect(config.MQTT_HOST, config.MQTT_PORT)
        payload = json.dumps({"valor": 25.0, "unidade": "%", "timestamp": time.time()})
        pub.publish(config.TOPIC_UMIDADE_SOLO, payload, qos=1)
        pub.disconnect()

        time.sleep(0.5)
        sub.loop_stop()
        sub.disconnect()

        assert len(recebido) >= 1
        assert recebido[0]["valor"] == 25.0


# Fix: importar os no escopo correto
import os
```

---

## Fase 8 — Scripts de Inicialização e Demonstração

**Agente responsável:** Fase 8  
**Pré-requisito:** Fases 1–7 concluídas

### 8.1 — Arquivo `scripts/start_all.ps1` (Windows)

Criar `trabalho_pratico1/scripts/start_all.ps1`:

```powershell
<#
.SYNOPSIS
    Inicia todos os componentes do sistema Estufa Agrícola Distribuída.
.DESCRIPTION
    Ordem de inicialização:
      1. Broker MQTT (Docker)
      2. Atuador
      3. Controladores (3 instâncias)
      4. Sensor (modo normal por padrão)
    O cliente deve ser iniciado manualmente após este script.
.PARAMETER modo_sensor
    Perfil do sensor: normal, seco, quente, frio (padrão: normal)
#>
param(
    [ValidateSet("normal","seco","quente","frio")]
    [string]$modo_sensor = "normal"
)

$ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "🌿 Iniciando Sistema Estufa Agrícola Distribuída..." -ForegroundColor Green
Write-Host ""

# 1. Broker MQTT
Write-Host "[1/5] Iniciando broker MQTT (Docker)..." -ForegroundColor Cyan
Push-Location $ROOT
docker compose up -d
Pop-Location
Start-Sleep -Seconds 2

# 2. Atuador
Write-Host "[2/5] Iniciando Atuador..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.atuador`"" -WindowStyle Normal

# 3. Controladores
Write-Host "[3/5] Iniciando Controladores (3 réplicas)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 300
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json`"" -WindowStyle Normal
Start-Sleep -Milliseconds 300
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json`"" -WindowStyle Normal
Start-Sleep -Seconds 1

# 4. Sensor
Write-Host "[4/5] Iniciando Sensor (modo: $modo_sensor)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '$ROOT'; python -m estufa.sensor --modo $modo_sensor`"" -WindowStyle Normal

Write-Host ""
Write-Host "[5/5] ✅ Sistema iniciado!" -ForegroundColor Green
Write-Host ""
Write-Host "Para iniciar o cliente, execute:" -ForegroundColor Yellow
Write-Host "    python -m estufa.cliente" -ForegroundColor White
Write-Host ""
Write-Host "Para demonstrar falha Byzantina:" -ForegroundColor Yellow
Write-Host "    python scripts\demo_byzantino.py" -ForegroundColor White
```

### 8.2 — Arquivo `scripts/start_all.sh` (Linux/macOS)

Criar `trabalho_pratico1/scripts/start_all.sh`:

```bash
#!/bin/bash
# start_all.sh — Inicia todos os componentes do sistema (Linux/macOS)

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODO_SENSOR="${1:-normal}"

echo "🌿 Iniciando Sistema Estufa Agrícola Distribuída..."
echo ""

# 1. Broker MQTT
echo "[1/5] Iniciando broker MQTT (Docker)..."
cd "$ROOT" && docker compose up -d
sleep 2

# 2. Atuador
echo "[2/5] Iniciando Atuador..."
cd "$ROOT" && python -m estufa.atuador &
PIDS=($!)

# 3. Controladores
echo "[3/5] Iniciando Controladores (3 réplicas)..."
cd "$ROOT" && python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json &
PIDS+=($!)
sleep 0.3
cd "$ROOT" && python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json &
PIDS+=($!)
sleep 0.3
cd "$ROOT" && python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json &
PIDS+=($!)
sleep 1

# 4. Sensor
echo "[4/5] Iniciando Sensor (modo: $MODO_SENSOR)..."
cd "$ROOT" && python -m estufa.sensor --modo "$MODO_SENSOR" &
PIDS+=($!)

echo ""
echo "[5/5] ✅ Sistema iniciado!"
echo ""
echo "PIDs dos processos: ${PIDS[@]}"
echo ""
echo "Para iniciar o cliente:"
echo "    python -m estufa.cliente"
echo ""
echo "Para parar todos os processos:"
echo "    kill ${PIDS[@]}"
echo "    docker compose down"
```

### 8.3 — Arquivo `scripts/demo_byzantino.py`

Criar `trabalho_pratico1/scripts/demo_byzantino.py`:

```python
"""
demo_byzantino.py — Demonstração de Tolerância a Falhas Byzantinas.

Este script:
  1. Consulta o estado com todos os 3 controladores normais (consenso esperado).
  2. Instrui o operador a reiniciar ctrl_2 em modo byzantino.
  3. Consulta o estado novamente e demonstra que o middleware detecta e ignora
     a resposta discrepante do nó byzantino, retornando o resultado correto.

Pré-condição:
  - Os 3 controladores devem estar rodando (portas 8001, 8002, 8003).
  - O sensor deve estar publicando dados.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from estufa.middleware import Middleware, ErroQuorum

def separador(titulo: str) -> None:
    print("\n" + "═" * 60)
    print(f"  {titulo}")
    print("═" * 60)

def exibir_estado(estado: dict, titulo: str = "Estado") -> None:
    print(f"\n{titulo}:")
    print(f"  🌡️  Temperatura:  {estado.get('temperatura', 'N/A')}")
    print(f"  💧 Umidade:      {estado.get('umidade_solo', 'N/A')}")
    print(f"  🚿 Bomba:        {'LIGADA' if estado.get('bomba_ligada') else 'DESLIGADA'}")
    print(f"  💨 Exaustor:     {'LIGADO' if estado.get('exaustor_ligado') else 'DESLIGADO'}")

mw = Middleware()

separador("FASE 1: Estado com todos os controladores normais")
print("Consultando estado via middleware (3 controladores normais)...")
try:
    estado = mw.obter_estado()
    exibir_estado(estado, "Resultado (consenso de 3/3)")
    print("\n✅ Votação bem-sucedida. Todos os controladores concordam.")
except ErroQuorum as e:
    print(f"❌ Erro: {e}")
    print("Certifique-se de que os 3 controladores estão rodando.")
    sys.exit(1)

separador("FASE 2: Simulando controlador Byzantino")
print("""
Para simular um controlador byzantino, abra um novo terminal e execute:

    # Pare o ctrl_2 e reinicie em modo byzantino:
    python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino

Aguardando... Pressione ENTER quando o ctrl_2 byzantino estiver rodando.
""")
input("▶ Pressione ENTER para continuar...")

separador("FASE 3: Votação com 1 nó byzantino (ctrl_2 mentindo)")
print("Consultando estado via middleware (ctrl_2 em modo byzantino)...")
print("  - ctrl_1 e ctrl_3: resposta legítima")
print("  - ctrl_2: resposta falsificada (temperatura=999, umidade=-1)")
print()

try:
    estado = mw.obter_estado()
    exibir_estado(estado, "Resultado após votação majoritária")
    print()
    print("✅ O middleware IGNOROU a resposta do ctrl_2 (byzantino).")
    print("   A maioria (ctrl_1 + ctrl_3) formou quorum e o resultado correto prevaleceu.")
    print()
    temp = estado.get("temperatura", 0)
    if temp < 100:
        print(f"   Temperatura={temp:.1f}°C (correto — não 999°C)")
    else:
        print(f"   ⚠️  Temperatura={temp} — verifique se o sensor está publicando dados.")
except ErroQuorum as e:
    print(f"❌ Erro de quorum: {e}")

separador("FASE 4: Simulando queda de ctrl_2 (nó offline)")
print("""
Agora feche o ctrl_2 (Ctrl+C no terminal do ctrl_2).
O sistema deve continuar funcionando com ctrl_1 e ctrl_3 (quorum 2/3).

Pressione ENTER quando o ctrl_2 estiver offline.
""")
input("▶ Pressione ENTER para continuar...")

try:
    estado = mw.obter_estado()
    exibir_estado(estado, "Resultado com ctrl_2 offline")
    print()
    print("✅ Sistema tolerou a queda do ctrl_2.")
    print("   ctrl_1 + ctrl_3 mantiveram o quorum (2/3).")
except ErroQuorum as e:
    print(f"❌ Erro de quorum: {e}")
    print("   2 controladores podem estar offline. Verifique ctrl_1 e ctrl_3.")

print("\n" + "═" * 60)
print("  🌿 Demonstração concluída!")
print("═" * 60 + "\n")
```

---

## Fase 9 — README e Relatório

**Agente responsável:** Fase 9  
**Pré-requisito:** Fases 1–8 concluídas

### 9.1 — Arquivo `README.md`

Criar `trabalho_pratico1/README.md` com o conteúdo **exato**:

```markdown
# Trabalho Prático 1 — Estufa Agrícola Distribuída

**Disciplina:** Sistemas Distribuídos  
**Tema:** Sistema de Controle de Estufa com MQTT e XML-RPC  
**Linguagem:** Python 3.9+  

---

## Tema e Contexto

Este projeto implementa um sistema distribuído de controle automático de uma **estufa agrícola**. O sistema monitora temperatura e umidade do solo em tempo real e aciona atuadores (bomba de irrigação e exaustor) conforme os thresholds configurados.

O trabalho explora na prática três desafios centrais de sistemas distribuídos:
1. **Comunicação heterogênea**: Sensores e atuadores comunicam via **MQTT** (pub/sub); clientes acessam o sistema via **XML-RPC** (invocação de métodos remotos).
2. **Replicação e tolerância à queda**: 3 réplicas do controlador garantem disponibilidade mesmo com 1 nó offline.
3. **Tolerância Byzantina**: Votação por maioria simples detecta e descarta respostas de controladores comprometidos.

---

## Arquitetura do Sistema

```
┌─────────────┐     MQTT (pub)      ┌──────────────────────────────────┐
│   Sensor    │ ──────────────────► │          Broker MQTT             │
│ (temp/umid) │                     │   (Eclipse Mosquitto / Docker)   │
└─────────────┘                     └──────────────────────────────────┘
                                           │ MQTT (sub)       ▲ MQTT (pub)
                                           ▼                  │
                              ┌────────────────────────┐      │
                              │  Controlador 1 (8001)  │      │
                              │  Controlador 2 (8002)  │      │
                              │  Controlador 3 (8003)  │ ─────┘
                              │   [JSON persistence]   │
                              └────────────────────────┘
                                           ▲ XML-RPC
                                           │
                              ┌────────────────────────┐
                              │       Middleware        │
                              │  (votação 2/3)         │
                              └────────────────────────┘
                                           ▲
                                           │ Invocação de métodos
                              ┌────────────────────────┐
                              │        Cliente         │
                              │    (CLI interativo)    │
                              └────────────────────────┘
                                                              ▼ MQTT (sub)
                              ┌──────────────────────────────────────────┐
                              │              Atuador                     │
                              │  (Bomba de Irrigação + Exaustor)         │
                              └──────────────────────────────────────────┘
```

---

## Estrutura de Arquivos

```
trabalho_pratico1/
│
├── docker-compose.yml          # Sobe o broker Mosquitto
├── mosquitto/
│   └── mosquitto.conf          # Configuração do broker
│
├── requirements.txt            # paho-mqtt, pytest
│
├── estufa/                     # Pacote principal
│   ├── __init__.py
│   ├── config.py               # Constantes: tópicos, portas, thresholds
│   ├── sensor.py               # Publica temp/umidade via MQTT
│   ├── atuador.py              # Assina comandos e executa ações
│   ├── controlador.py          # XML-RPC Server + MQTT consumer + lógica + JSON
│   ├── middleware.py           # Votação majoritária (BFT simplificado)
│   └── cliente.py              # CLI do usuário
│
├── tests/
│   ├── __init__.py
│   ├── test_controlador.py     # Testes unitários do controlador
│   ├── test_middleware.py      # Testes de votação e tolerância a falhas
│   └── test_integracao.py      # Testes end-to-end (com e sem broker)
│
├── scripts/
│   ├── start_all.ps1           # Inicia tudo (Windows)
│   ├── start_all.sh            # Inicia tudo (Linux/macOS)
│   └── demo_byzantino.py       # Demonstração interativa de BFT
│
├── relatorio/
│   └── relatorio.md            # Relatório completo do trabalho
│
└── README.md                   # Este arquivo
```

---

## Pré-requisitos

- Python 3.9 ou superior
- Docker Desktop (para o broker Mosquitto)
- pip

```bash
pip install -r requirements.txt
```

---

## Como Executar

### 1. Subir o broker MQTT

```bash
docker compose up -d
```

### 2. Iniciar todos os componentes (Windows)

```powershell
# Modo padrão (sensor com dados normais)
.\scripts\start_all.ps1

# Sensor simulando solo seco (aciona bomba automaticamente)
.\scripts\start_all.ps1 -modo_sensor seco

# Sensor simulando calor extremo (aciona exaustor automaticamente)
.\scripts\start_all.ps1 -modo_sensor quente
```

### 3. Iniciar o cliente (menu interativo)

```bash
python -m estufa.cliente
```

### 4. Modo automático (dashboard)

```bash
python -m estufa.cliente --auto --intervalo 3
```

### 5. Iniciar componentes individualmente

```bash
# Atuador
python -m estufa.atuador

# Controladores (3 instâncias — abra 3 terminais)
python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json
python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json
python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json

# Sensor
python -m estufa.sensor --modo normal

# Controlador em modo Byzantino (demonstração)
python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json --byzantino
```

---

## Tópicos MQTT

| Tópico | Direção | Descrição |
|---|---|---|
| `estufa/sensores/temperatura` | Sensor → Controlador | Leitura de temperatura (°C) |
| `estufa/sensores/umidade_solo` | Sensor → Controlador | Leitura de umidade do solo (%) |
| `estufa/atuadores/bomba` | Controlador → Atuador | Comando: ligar/desligar bomba |
| `estufa/atuadores/exaustor` | Controlador → Atuador | Comando: ligar/desligar exaustor |
| `estufa/status/bomba` | Atuador → (log) | Confirmação de execução da bomba |
| `estufa/status/exaustor` | Atuador → (log) | Confirmação de execução do exaustor |

---

## Portas XML-RPC dos Controladores

| Controlador | Porta | Arquivo de Dados |
|---|---|---|
| ctrl_1 (principal) | 8001 | data_ctrl_1.json |
| ctrl_2 (réplica) | 8002 | data_ctrl_2.json |
| ctrl_3 (réplica) | 8003 | data_ctrl_3.json |

---

## Thresholds de Controle

| Parâmetro | Valor | Ação |
|---|---|---|
| Temperatura máxima | 35°C | Liga exaustor |
| Temperatura mínima | 15°C | Desliga exaustor |
| Umidade mínima | 30% | Liga bomba |
| Umidade máxima | 70% | Desliga bomba |

---

## Executar Testes

```bash
# A partir do diretório trabalho_pratico1/
python -m pytest tests/ -v

# Apenas testes unitários (sem broker):
python -m pytest tests/test_controlador.py tests/test_middleware.py -v

# Com relatório de cobertura:
python -m pytest tests/ -v --tb=short
```

> **Os testes `test_controlador.py` e `test_middleware.py` são completamente autocontidos**: não requerem broker MQTT nem nenhum processo externo.  
> **Os testes `test_integracao.py`** que requerem broker são automaticamente pulados se o Docker não estiver rodando.

---

## Demonstração de Tolerância Byzantina

```bash
# Com os 3 controladores normais rodando:
python scripts/demo_byzantino.py
```

O script guia o operador pelos 3 cenários:
1. Todos os nós normais → consenso de 3/3
2. ctrl_2 em modo byzantino → middleware detecta e usa maioria de 2/3
3. ctrl_2 offline → sistema continua com ctrl_1 + ctrl_3

---

## Dependências

```
paho-mqtt==2.1.0
pytest==8.3.3
pytest-timeout==2.3.1
```
```

### 9.2 — Arquivo `relatorio/relatorio.md`

Criar `trabalho_pratico1/relatorio/relatorio.md` com o conteúdo **exato**:

```markdown
# Relatório — Trabalho Prático 1: Estufa Agrícola Distribuída

**Disciplina:** Sistemas Distribuídos  
**Tema:** Estufa Agrícola com MQTT e XML-RPC  

---

## 1. Apresentação do Tema

O tema escolhido é o controle automatizado de uma **estufa agrícola**. Uma estufa de alto valor (por exemplo, produção de orquídeas ou mudas medicinais) exige monitoramento contínuo de temperatura e umidade do solo. Falhas no controle podem destruir plantações inteiras em horas.

O sistema distribui a responsabilidade por esse controle entre múltiplos nós de forma tolerante a falhas, garantindo que:
- A estufa continue sendo controlada mesmo que um controlador falhe.
- Um controlador comprometido (por ataque ou falha parcial) não consiga enviar comandos errados.

### Funcionamento Geral

1. **Sensores** publicam leituras de temperatura e umidade a cada 2 segundos via MQTT.
2. **Controladores** recebem as leituras, tomam decisões e publicam comandos para os atuadores.
3. **Atuadores** recebem os comandos e executam as ações físicas (ligar bomba, ligar exaustor).
4. **Clientes** consultam e comandam o sistema através do **Middleware**, sem saber quantos controladores existem.

---

## 2. Replicação de Dados

### Mecanismo Adotado

O sistema possui **3 instâncias independentes do Controlador** (ctrl_1, ctrl_2, ctrl_3), cada uma:
- Assinando os mesmos tópicos MQTT dos sensores
- Aplicando a mesma lógica de decisão de forma independente
- Persistindo o estado atual em seu próprio arquivo JSON local (`data_ctrl_N.json`)

Essa replicação é do tipo **replicação ativa** (ou replicação de estado-máquina simplificada): todos os nós processam as mesmas entradas e chegam ao mesmo estado independentemente.

### Por que 3 Réplicas?

O número mínimo para suportar **1 falha Byzantina** com votação por maioria é `3f + 1 = 3(1) + 1 = 4`. No entanto, para o modelo simplificado (apenas crash faults e 1 Byzantine a detectar, não a tolerar com operação plena), 3 réplicas atingem quorum de 2/3 que é suficiente para as exigências do trabalho:

- Tolerar **queda de 1 nó**: 2 dos 3 restantes formam quorum.
- Detectar **1 nó byzantine**: 2 honestos vs 1 desonesto → maioria prevalece.

---

## 3. Tolerância à Queda de Controlador

### Problema

O cliente invoca um método remoto no cluster de controladores. Se um dos controladores cair durante a execução, a resposta não pode ser perdida.

### Solução Implementada

O **Middleware** envia a chamada XML-RPC para **todos os 3 controladores em paralelo** (usando `concurrent.futures.ThreadPoolExecutor`). Cada chamada tem um timeout individual de 3 segundos.

- Se o controlador cair: a chamada lança uma exceção de conexão após o timeout, e aquela resposta é **descartada**.
- O middleware aguarda as demais respostas e verifica se há **quorum mínimo de 2 respostas concordantes**.
- Se o quorum for atingido (ex: 2 de 3 responderam e concordam), o resultado é retornado ao cliente.
- O cliente **não percebe** a queda do controlador.

### Sequência de Eventos (Queda do ctrl_2)

```
Cliente → Middleware.obter_estado()
Middleware → [Thread-1: XML-RPC ctrl_1:8001] → resposta OK em 50ms
Middleware → [Thread-2: XML-RPC ctrl_2:8002] → TIMEOUT após 3s (nó caído)
Middleware → [Thread-3: XML-RPC ctrl_3:8003] → resposta OK em 55ms
Middleware: 2 respostas concordantes ≥ quorum(2) → retorna resultado
Cliente ← resultado correto (sem erro)
```

---

## 4. Tolerância a Falhas Byzantinas

### Problema

Um controlador pode ser comprometido por um ataque cibernético ou falha de software e começar a retornar valores incorretos (ex: temperatura=999°C, bomba=desligada quando deveria estar ligada). Se o middleware simplesmente pegasse a resposta do primeiro controlador disponível, esse valor falso seria repassado ao cliente ou usado para tomar decisões erradas.

### Solução Implementada: Votação por Maioria Simples

O middleware implementa votação por maioria na função `_votar()`:

1. Coleta respostas de todos os controladores em paralelo.
2. **Normaliza** cada resposta para uma string JSON comparável (removendo campos voláteis como `ultima_atualizacao`).
3. Conta os votos usando `collections.Counter`.
4. Verifica se a resposta mais comum possui **≥ QUORUM_MINIMO (2) votos**.
5. Se sim, retorna essa resposta. Se não, levanta `ErroQuorum`.

### Exemplo de Votação (ctrl_2 Byzantino)

```
ctrl_1 responde: {temperatura: 28.5, umidade: 45.0, ...}  → voto A
ctrl_2 responde: {temperatura: 999.0, umidade: -1.0, ...}  → voto B  ← byzantino
ctrl_3 responde: {temperatura: 28.5, umidade: 45.0, ...}  → voto A

Contagem: {A: 2, B: 1}
Maioria: A (2 votos ≥ quorum de 2)
→ Retorna resposta A. O cliente recebe dados corretos.
```

### Modo Byzantino para Demonstração

O controlador pode ser iniciado com `--byzantino`, que faz com que:
- `obter_estado()` retorne temperatura=999 e umidade=-1.
- `comandar_bomba()` e `comandar_exaustor()` retornem confirmação falsa sem executar a ação.

Isso permite demonstrar o mecanismo de detecção durante a apresentação.

---

## 5. Conclusão

O sistema implementado demonstra na prática os três desafios de Sistemas Distribuídos exigidos pelo trabalho:

| Desafio | Solução |
|---|---|
| Replicação de dados | 3 controladores independentes com persistência JSON própria |
| Tolerância à queda | Middleware com chamadas paralelas e quorum de 2/3 |
| Tolerância Byzantina | Votação por maioria simples com normalização de respostas |

A separação entre a camada MQTT (sensores/atuadores) e a camada XML-RPC (cliente/middleware/controlador) demonstra a integração de dois paradigmas de comunicação distintos em um mesmo sistema distribuído.
```

---

## Fase 10 — Verificação Final e Execução dos Testes

**Agente responsável:** Fase 10  
**Pré-requisito:** Fases 1–9 concluídas

### 10.1 — Instalar dependências

```powershell
cd d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\trabalho_pratico1
pip install -r requirements.txt
```

### 10.2 — Verificar estrutura de arquivos

```powershell
Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch '__pycache__' } | Select-Object FullName
```

**Saída esperada** (todos os arquivos):
- `docker-compose.yml`
- `mosquitto\mosquitto.conf`
- `requirements.txt`
- `estufa\__init__.py`
- `estufa\config.py`
- `estufa\sensor.py`
- `estufa\atuador.py`
- `estufa\controlador.py`
- `estufa\middleware.py`
- `estufa\cliente.py`
- `tests\__init__.py`
- `tests\test_controlador.py`
- `tests\test_middleware.py`
- `tests\test_integracao.py`
- `scripts\start_all.ps1`
- `scripts\start_all.sh`
- `scripts\demo_byzantino.py`
- `relatorio\relatorio.md`
- `README.md`

### 10.3 — Executar testes unitários (sem broker)

```powershell
cd d:\Users\0105202\Documents\Projects\projetos-sistemas-distribuidos\trabalho_pratico1
python -m pytest tests/test_controlador.py tests/test_middleware.py -v
```

**Resultado esperado:** Todos os testes PASSAM (nenhum broker necessário).

### 10.4 — Subir broker e executar testes de integração

```powershell
docker compose up -d
python -m pytest tests/test_integracao.py -v
docker compose down
```

**Resultado esperado:** Testes `TestIntegracaoComBrokerReal` PASSAM. `TestDecisaoComDadosSensorSimulados` já passou na etapa anterior.

### 10.5 — Executar todos os testes juntos

```powershell
docker compose up -d
python -m pytest tests/ -v --tb=short
docker compose down
```

### 10.6 — Validação manual rápida (smoke test)

```powershell
# Terminal 1: Broker
docker compose up -d

# Terminal 2: Atuador
python -m estufa.atuador

# Terminal 3: ctrl_1
python -m estufa.controlador --id ctrl_1 --port 8001 --data data_ctrl_1.json

# Terminal 4: ctrl_2
python -m estufa.controlador --id ctrl_2 --port 8002 --data data_ctrl_2.json

# Terminal 5: ctrl_3
python -m estufa.controlador --id ctrl_3 --port 8003 --data data_ctrl_3.json

# Terminal 6: Sensor (modo seco para acionar bomba)
python -m estufa.sensor --modo seco

# Terminal 7: Cliente
python -m estufa.cliente
# → Opção 1 (consultar estado) deve mostrar bomba LIGADA
# → Opção 6 (verificar saúde) deve mostrar os 3 controladores como "ok"
```

---

## Resumo das Decisões de Design

| Decisão | Escolha | Justificativa |
|---|---|---|
| Broker MQTT | Eclipse Mosquitto (Docker) | Leve, padrão de mercado, configuração mínima |
| Comunicação cliente-controlador | XML-RPC nativo Python | Zero dependências extras, fácil de inspecionar |
| Réplicas | 3 controladores | Mínimo para detectar 1 Byzantine com votação por maioria |
| Consenso | Votação por maioria (2/3) | Simples de implementar, suficiente para 1 falha |
| Persistência | JSON por controlador | Legível, sem ORM, facilita inspeção manual |
| Execução | Processos separados | Realista, simula distribuição em máquinas distintas |
| Testes | pytest + mocks internos | Autocontidos, sem broker para testes unitários |
