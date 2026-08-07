# Explicação Detalhada do Código — Atividade Prática 1 (Sistemas Distribuídos)

Este documento foi preparado para servir de roteiro ou material de apoio para a apresentação do código desenvolvido. A atividade consiste em um sistema de troca de mensagens cliente-servidor através de **sockets TCP**, com o objetivo de demonstrar a serialização e desserialização de dados usando cinco formatos distintos baseados em texto: **CSV, JSON, XML, YAML e TOML**.

---

## 1. Visão Geral da Arquitetura e do Protocolo

Para que o servidor consiga saber exatamente o tamanho da mensagem que está sendo enviada pelo cliente (já que no TCP os dados fluem como um fluxo contínuo de bytes) e qual o formato dessa mensagem, foi estabelecido um protocolo simples (um cabeçalho customizado) com a seguinte estrutura:

**Wire Format (Formato de Transmissão):**
```text
[ 4 bytes: tamanho do payload ] + [ 10 bytes: formato ] + [ N bytes: dados serializados ]
```

1. **4 bytes iniciais:** Representam um inteiro sem sinal (usando `struct.pack('>I', ...)`) que indica o comprimento da mensagem serializada.
2. **10 bytes seguintes:** Representam o nome do formato como uma string de tamanho fixo (ex: `"csv       "`, `"json      "`).
3. **Payload:** A string (em bytes) do dado propriamente serializado.

---

## 2. Implementação do Cliente (`client.py`)

O cliente tem o papel de pegar um dicionário Python (os dados do usuário) e enviá-lo 5 vezes, cada vez empacotado em um formato de serialização diferente.

### 2.1. Funções de Serialização
Para cada um dos 5 formatos, há uma função dedicada que converte o dicionário Python `DADOS` em uma representação textual.

- **CSV (`serialize_csv`)**: Utiliza as classes `io.StringIO()` e `csv.DictWriter` (da biblioteca padrão) para gerar uma string com cabeçalho e os valores separados por vírgula.
- **JSON (`serialize_json`)**: Utiliza `json.dumps()` (da biblioteca padrão). O parâmetro `indent=2` formata a string para exibição amigável, e `ensure_ascii=False` garante a codificação correta dos acentos.
- **XML (`serialize_xml`)**: Utiliza `xml.etree.ElementTree` (biblioteca padrão). Cria um elemento raiz `<pessoa>` e itera sobre as chaves do dicionário para criar os subelementos.
- **YAML (`serialize_yaml`)**: Utiliza a biblioteca externa `pyyaml` (importada como `yaml`). Chama a função `yaml.dump()` que traduz o dicionário em um bloco estruturado usando espaços.
- **TOML (`serialize_toml`)**: Como a biblioteca padrão (em versões antigas) não escreve TOML diretamente, utiliza-se a biblioteca `tomli_w`. O TOML exige uma seção estruturada, então encapsulamos os dados num nível extra `{'pessoa': {...}}`.

### 2.2. Envio das Mensagens
A função `send_message(sock, fmt, data_str)` implementa o nosso protocolo customizado:
1. Converte os dados formatados (string) em `bytes` UTF-8.
2. Completa (pad) o nome do formato (ex: `csv`) para que tenha exatamente 10 bytes usando `.ljust(10)`.
3. Calcula o tamanho do payload e empacota esse inteiro nos primeiros 4 bytes do cabeçalho com `struct.pack('>I')`.
4. Envia tudo pela rede: `header (tamanho) + formato + payload`.

No laço `main()`, o cliente itera sobre a lista de serializadores, formata a mensagem, chama `send_message` e aguarda o servidor responder invocando `recv_ack`.

---

## 3. Implementação do Servidor (`server.py`)

O servidor aguarda passivamente que um cliente se conecte, extrai os dados, descobre em qual formato estão e então os converte novamente (desserializa) para serem exibidos na tela.

### 3.1. Tratamento da Conexão e do Protocolo
- O servidor fica no aguardo na porta definida via `s.accept()`.
- O método `recv_message(conn)` é o inverso perfeito do envio feito pelo cliente. Ele é o núcleo do recebimento:
  1. Lê exatamente 4 bytes (`recv_all(conn, 4)`) e desempacota o tamanho da string.
  2. Lê os 10 bytes e extrai o nome do formato.
  3. Com base no tamanho lido no passo 1, lê exatamente aquele número de bytes da rede (o payload).
  4. Retorna o formato detectado e a string decodificada.

### 3.2. Handlers de Exibição (Desserialização)
O uso inteligente do dicionário `DISPLAY_HANDLERS` mapeia a string do formato (ex: `"json"`) para a função de renderização correspondente (`display_json`), evitando o uso excessivo de condições `if-else`.

Em cada handler `display_*`:
- A desserialização ocorre usando bibliotecas correspondentes (`json.loads`, `csv.DictReader`, `ET.fromstring`, `yaml.safe_load`, `tomllib.loads`).
- Foi implementada uma lógica de estilo (usando códigos de escape ANSI) para desenhar painéis e colorir os resultados no terminal, o que ajuda na visualização diferenciada de cada formato e na depuração.

Após receber uma mensagem, e exibi-la de forma correta, o servidor constrói uma mensagem de confirmação no formato `ACK:FORMATO:OK` e envia de volta ao cliente. Como a conexão tem o comportamento esperado, ela é finalizada assim que as 5 requisições do cliente terminam e ele se desconecta.

---

## 4. Destaques da Solução (Para a Apresentação)

Durante a apresentação, vale a pena enfatizar os seguintes pontos na sua arquitetura:

- **Robusteza do Protocolo de Comunicação**: Citar o uso do prefixo de tamanho (*length-prefix framing*). No TCP/IP, dados são streams sem bordas naturais; enviar primeiro o "tamanho" da mensagem previne que o servidor fique bloqueado e garante que mensagens agrupadas no buffer de rede (efeito Nagle, etc.) não sejam truncadas e se tornem inválidas.
- **Tolerância a Falhas nas Bibliotecas**: O servidor (assim como o cliente) trata a importação de bibliotecas externas (como `yaml` e `tomli`) com blocos `try/except ImportError`. Assim o script não quebra brutalmente se as dependências não estiverem instaladas; ele apenas informa o que está faltando.
- **Modularidade**: A clara separação no cliente de um array de tuplas chamado `SERIALIZERS` permite que a inclusão de um 6º formato no futuro dependesse da criação de apenas mais uma função sem alterar as regras de conexão de rede.
