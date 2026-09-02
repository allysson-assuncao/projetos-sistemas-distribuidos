# Análise e Checklist Final: AP3 — MQTT Casa Inteligente

Abaixo está o detalhamento de tudo que construímos em conjunto e a lista exata do que ainda precisa ser realizado para concluir e apresentar o trabalho com nota máxima, com base nos critérios de avaliação oficiais.

## ✅ O que já foi feito (Implementado e Automatizado)

- [x] **Broker Mosquitto Local**: Configurado localmente via Docker (`docker-compose.yml`).
- [x] **Taxonomia de Tópicos**: Criada hierarquia extensível (`casa/sala/temperatura`, `casa/frente/porta`, `casa/status/sensores`), contemplando também uso de wildcards (`casa/#`).
- [x] **Múltiplos Clientes**: Construídos 4 clientes em processos separados, todos com `client_id` claro (`pub_temperatura`, `pub_porta`, `sub_alarme`, `sub_dashboard`).
- [x] **Estrutura de Envelope (Payload)**: JSON padronizado com Identificador único do sensor, número de sequência (`seq`) para validação, e timestamp.
- [x] **Níveis de QoS**: Sistema totalmente parametrizado para suportar QoS 0, 1 e 2.
- [x] **Indisponibilidade e Retenção**: 
  - *Retained Messages* implementadas no sensor de porta.
  - *LWT (Last Will and Testament)* parametrizado para reportar quedas súbitas (sensor offline).
- [x] **Orquestração e Evidências**: Criados os scripts `run_experiment.py` (para rodar todas as amostras sozinhas) e `analyze.py` (para cruzar as perdas de pacote x QoS em CSV, Tabela MD e Gráficos PNG).
- [x] **README de Execução**: Preparado e anexado à raiz do repositório contendo diagrama de arquitetura e explicações de instalação.

---

## ⏳ Pendências: O que VOCÊ deve fazer

Nesta etapa, o trabalho deixa de ser puramente de codificação e passa a exigir compreensão acadêmica e defesa técnica. 

### 1. Obrigatório ANTES do Envio (Análise)
O critério "Análise" exige diferenciar a entrega de transporte (o que o MQTT garante) do efeito no negócio. Para isso, vá até o arquivo `README.md` (no final dele) e responda de forma dissertativa as 5 questões:
- [ ] **Desacoplamento**: Explicar a separação temporal/espacial que o Broker possibilita.
- [ ] **QoS no domínio**: Justificar se perder um dado de temperatura (QoS 0) é aceitável em detrimento à performance.
- [ ] **Duplicatas**: Explicar por que o QoS 1 pode reentregar mensagens e como a chave `seq` no JSON permite identificar isso (já que "exactly once" no transporte não garante processamento único).
- [ ] **Retained**: Citar por que a porta ter estado retido ajuda (quem chega depois não precisa esperar ela abrir de novo) e onde poderia ser perigoso usar retain.
- [ ] **Ponto de Falha**: Refletir sobre como a queda do Broker Mosquitto cessa toda a rede, sugerindo abordagens de mercado (clusterização de brokers, bridge, etc).

### 2. Obrigatório ANTES do Envio (Gerar Evidências Finais)
Como o projeto está recém-criado, você precisa rodar a bateria final de testes no seu computador para anexá-los:
- [ ] Rode o broker: `docker compose up -d` na pasta `broker`.
- [ ] Execute `python experiments/run_experiment.py` (irá demorar alguns minutos para coletar as amostras de QoS 0, 1, 2 e as quedas do LWT).
- [ ] Execute `python analysis/analyze.py` para consolidar as tabelas e as fotos gráficas na pasta `analysis/output/`. 

### 3. Obrigatório DURANTE a Apresentação
O critério "Demonstração" pontua cenário reproduzível e bem explicado.
- [ ] Revise o código de `sub_alarme.py` para entender como o número de sequência (`seq`) é usado para somar as métricas de perda de pacotes e duplicatas.
- [ ] Esteja pronto para rodar o comando `python src/pub_porta.py --simulate-crash` ao vivo na frente do professor. Isso matará o processo abruptamente, disparando a rotina automática que avisa o alarme que a porta ficou OFFLINE (LWT).
- [ ] Esteja pronto para explicar o diagrama da arquitetura (disponível no README).

---

## 🚀 Desafios Opcionais (Como Melhorar e Encantar)

As instruções trazem 3 desafios extras. Caso deseje um "10" com louvor, após terminar as pendências acima você pode investir em:

- **Autenticação (Segurança MQTT)**: Remover `allow_anonymous true` do `mosquitto.conf`, criando senhas ou restrições via ACL (Access Control List) para que o Sensor de Porta não possa escrever no tópico de Temperatura, por exemplo.
- **Banco de Dados (Persistência)**: Implementar uma rotina no Subscriber (usando SQLite) para guardar os estados, adicionando lógica idempotente (um IF que checa se o número sequencial daquela mensagem já está no banco antes de gravar).
- **Update para MQTT V5**: Utilizar o protocolo em sua versão mais recente, explorando injeção de metadata nos cabeçalhos em vez do corpo do payload.
