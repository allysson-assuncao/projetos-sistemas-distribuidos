# Report — Atividade Prática 4: gRPC Digital Wallet Service
**Course:** Sistemas Distribuídos  
**Topic:** Digital Wallet  
**Technology:** gRPC + Protocol Buffers (Python)

---

## 1. Comparativo: gRPC vs REST vs MQTT

Esta Atividade Prática explorou a implementação de chamadas remotas através do gRPC e Protocol Buffers, estabelecendo um forte contraste com os modelos estudados anteriormente. Em comparação ao **REST (AP2)**, que é orientado a recursos (com verbos HTTP) e tipicamente trafega dados em JSON sem validação inerente de schema nativa do protocolo, o gRPC adota um modelo *schema-first* voltado à invocação direta de funções. Ele utiliza transporte binário via HTTP/2, provendo latência reduzida e menor tamanho de payload, além de tipagem estrita gerada automaticamente. 

Por outro lado, contrastando com o **MQTT (AP3)**, que é um protocolo assíncrono baseado em *publish/subscribe* projetado para tolerância a quedas de conectividade e cenários IoT, o gRPC prioriza a comunicação síncrona (request-response) backend-to-backend, exigindo acoplamento de interface forte entre cliente e servidor em troca de velocidade e robustez no contrato.

---

## 2. Experiment Results Table

| # | Experiment             | RPC Method                   | Observed gRPC Status     | Latency (ms)   | Notes                                                      |
|---|------------------------|------------------------------|--------------------------|----------------|------------------------------------------------------------|
| 1 | Unavailability         | ConsultarSaldo               | `UNAVAILABLE`            | 2300.4         | Server stopped. Immediate error after connection timeout |
| 2a| Deadline (short)       | Depositar (timeout=1s)       | `DEADLINE_EXCEEDED`      | 1030.4         | Server delay=3s. Client cancels after 1s                 |
| 2b| Deadline (sufficient)  | Depositar (timeout=5s)       | `OK`                     | 3004.2         | Server delay=3s. Completed within timeout                |
| 3 | Concurrency (20 cli.)  | Depositar (×20 simultaneous) | 20/20 `OK`               | 6.6            | Workers=20. All processed without errors                 |
| 4 | Contract Evolution     | Depositar (field `moeda`)    | `OK`                     | 4.7            | New field ignored by old server — backward-compatible    |

---

## 3. Questões para Análise

### Q1. Por que uma chamada remota não deve ser tratada como função local?

Uma chamada remota (RPC) opera sobre uma rede, um meio **não confiável e não determinístico**, o que cria três classes de falhas fundamentalmente ausentes em chamadas locais:

1. **Falhas de rede:** pacotes podem ser perdidos, reordenados ou atrasados. Uma função local nunca "some no meio do caminho".
2. **Falhas parciais:** o servidor pode receber a requisição, processar o pedido e depois falhar *antes* de enviar a resposta. O cliente não sabe se a operação foi executada ou não. Esse estado de **incerteza** é impossível em chamadas locais, onde uma exceção não deixa dúvidas sobre se o código rodou.
3. **Latência variável e deadline:** chamadas locais têm latência de nanossegundos. Chamadas remotas podem levar centenas de milissegundos e precisam de **timeout** explícito — caso contrário, o cliente pode bloquear indefinidamente. O gRPC resolve isso com o mecanismo de **deadline propagado** via metadados HTTP/2.

A **transparência de acesso** (fazer RPCs parecerem funções locais) foi o objetivo dos primeiros sistemas RPC (DCE, CORBA), mas foi considerada uma **falácia** pelo manifesto das "8 Falácias da Computação Distribuída" (Deutsch, 1994). O gRPC adota a postura oposta: erros de rede são explicitamente modelados como `StatusCode` (UNAVAILABLE, DEADLINE_EXCEEDED), forçando o desenvolvedor a tratar cada cenário de falha individualmente.

---

### Q2. Qual diferença entre erro de aplicação e indisponibilidade do serviço?

São categorias **semanticamente distintas** com implicações de tratamento completamente diferentes:

| Dimensão           | Erro de Aplicação                               | Indisponibilidade do Serviço                    |
|--------------------|------------------------------------------------|-------------------------------------------------|
| **Status gRPC**    | `INVALID_ARGUMENT`, `NOT_FOUND`, `ALREADY_EXISTS`, `FAILED_PRECONDITION` | `UNAVAILABLE`, `DEADLINE_EXCEEDED`              |
| **Causa**          | Dados inválidos fornecidos pelo cliente; violação de regra de negócio | Servidor desligado, rede particionada, timeout  |
| **Servidor**       | Recebeu e processou a requisição                | Não recebeu, ou não conseguiu responder          |
| **Retry seguro?**  | **Não** (novo erro com os mesmos dados)         | **Possivelmente** (servidor pode ter voltado)   |
| **Ação correta**   | Corrigir os dados e tentar novamente            | Exponential backoff + circuit breaker           |
| **Exemplo neste AP4** | Saque com saldo insuficiente (`FAILED_PRECONDITION`) | Servidor parado (`UNAVAILABLE`) no Experimento 1 |

**Por que a distinção importa?** Se um depósito retorna `UNAVAILABLE`, o cliente pode tentar novamente — o dinheiro possivelmente ainda não foi creditado. Se retorna `ALREADY_EXISTS`, tentar novamente não mudará o resultado. Confundir as duas categorias leva a bugs graves: re-tentar um erro de aplicação desperdiça recursos; não re-tentar uma indisponibilidade causa perda de dados.

---

### Q3. O contrato forte aumenta qual tipo de acoplamento?

O uso de um contrato fortemente tipado com Protocol Buffers aumenta o **acoplamento de interface** (também chamado de *schema coupling* ou *representational coupling*). Este é o tipo de acoplamento que exige que cliente e servidor **concordem explicitamente sobre os tipos de dados, nomes de campos e estrutura das mensagens**.

**Por que isso é diferente de outros acoplamentos:**

- **Acoplamento temporal** (um componente precisa do outro disponível ao mesmo tempo): gRPC não agrava isso além do necessário para o paradigma request-response.
- **Acoplamento de implementação** (um componente conhece os internos de outro): gRPC reduz isso — o cliente só conhece a interface `.proto`, não a implementação do servidor.
- **Acoplamento de schema** (o que gRPC aumenta): o cliente *deve* conhecer a estrutura exata das mensagens. Qualquer renomeação de campo ou mudança de número de campo quebra os consumidores.

**Custo vs. Benefício:** O schema coupling introduzido pelo gRPC tem um custo real — exige que todos os consumidores regenerem seus stubs a cada mudança de contrato. O benefício é que esse custo se torna **explícito, gerenciável e verificável em tempo de compilação**, em vez de ser descoberto em runtime como ocorre com REST/JSON. O Protobuf minimiza o impacto com **backward compatibility por design** (campos novos têm IDs únicos; campos desconhecidos são ignorados), mas renomear ou remover campos *sempre* é uma mudança incompatível.

---

### Q4. Como você faria retry sem duplicar efeitos perigosos?

O risco central do retry é a **duplicação de efeitos não idempotentes**. Um `Depositar` reenviado duas vezes crédita o valor duas vezes; um `Sacar` reenviado duas vezes debita o dobro. A solução é **garantir idempotência no servidor**:

**Estratégia: Idempotency Key (chave de idempotência)**

1. O cliente gera um **UUID único** por tentativa de operação lógica (não por chamada de rede). Esse UUID é incluído nos metadados gRPC ou no corpo da mensagem (ex: `idempotency_key` como campo `string` no `TransacaoRequest`).
2. O servidor mantém um **registro de operações processadas** (cache com TTL, ex: Redis ou tabela de banco de dados) mapeando `idempotency_key → resultado`.
3. Ao receber uma requisição:
   - Se `idempotency_key` **não existe** no registro → processa normalmente, salva o resultado.
   - Se `idempotency_key` **já existe** no registro → retorna o resultado já salvo, sem processar novamente.
4. O cliente pode re-enviar com o **mesmo UUID** quantas vezes quiser após `UNAVAILABLE` ou `DEADLINE_EXCEEDED`. O servidor garante que o efeito real ocorrerá no máximo uma vez.

**No contexto deste AP4:** Os métodos `CriarConta` e `ConsultarSaldo` já são naturalmente idempotentes (`CriarConta` retorna `ALREADY_EXISTS` na segunda chamada). `Depositar`, `Sacar` e `Transferir` não são — e exigiriam a estratégia acima em um sistema de produção. Combinado com **exponential backoff** (esperar 1s, 2s, 4s... entre tentativas) e **circuit breaker** (parar de tentar após N falhas consecutivas), o retry se torna seguro e eficiente.

---

### Q5. Que mudança no .proto seria incompatível?

O Protocol Buffers garantem compatibilidade **apenas para certas operações**. As seguintes mudanças são **sempre incompatíveis** (quebram clientes ou servidores existentes):

| Mudança incompatível                        | Por quê quebra                                                                         |
|---------------------------------------------|----------------------------------------------------------------------------------------|
| **Renomear um campo**                       | O nome do campo é usado em JSON/texto; em binário, o *número* é usado — mas renomear força regeneração de stubs e quebra código gerado anterior |
| **Mudar o número de um campo (tag)**        | O payload binário usa o número do campo para mapear dados. Mudar o número desserializa os dados para o campo errado. |
| **Mudar o tipo do campo**                   | Exemplo: trocar de `string` para `int32`. O parser falhará ao ler bytes como inteiros ou vice-versa. |
| **Remover um campo e reusar seu número**    | Clientes antigos enviando o campo original farão o servidor populá-lo no novo campo, causando corrupção de dados. |

Para manter a compatibilidade ao remover campos, deve-se marcá-lo usando a palavra-chave `reserved`, garantindo que o número (e o nome) jamais sejam reaproveitados acidentalmente no futuro.
