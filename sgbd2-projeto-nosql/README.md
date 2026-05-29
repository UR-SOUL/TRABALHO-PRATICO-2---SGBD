# Camada de Persistência para E-commerce de Alta Escala
## Subdomínio: Carrinho de Compras e Gestão de Sessões

**Disciplina:** Sistemas de Gestão de Bases de Dados II (SGBD II)  
**Docente:** Moyo Kanivengidio  
**Ano Letivo:** 2025/2026  
**Tecnologia:** Redis 7.2 em modo Cluster (3 masters + 3 réplicas)  
**Grupo:** Ariel Alfredo da Cunha Manuel | Matondo Kuanzambi Samuel João | Nzongo Oceano Nsumbo Manuel | Pedro Bengui  

---

## Descrição do Projeto

Este projeto implementa uma camada de persistência NoSQL para o subdomínio de
Carrinho de Compras e Gestão de Sessões de uma plataforma de e-commerce de alta
escala. A solução utiliza Redis Cluster com sharding automático por hash slots e
replicação assíncrona, demonstrando os princípios do Teorema CAP e do modelo
PACELC aplicados a um cenário real.

O sistema suporta 11 padrões de acesso distintos, foi testado com 100.000 sessões
e 100.000 carrinhos (200.001 chaves no total), e demonstrou disponibilidade de
100% durante simulação de falha de nó master.

---

## Estrutura do Repositório

```
sgbd2-projeto-nosql/
|
|-- docker/
|   |-- docker-compose.yml        # Orquestracao do Redis Cluster (6 nos)
|   |-- redis-cluster-init.sh     # Script alternativo de inicializacao manual
|
|-- scripts/
|   |-- seeding.py                # Geracao e insercao de 100.000 registos
|   |-- queries.py                # Implementacao dos 11 padroes de acesso
|   |-- benchmark.py              # Testes de desempenho e tolerancia a falhas
|
|-- relatorio/
|   |-- Relatorio.pdf             # Relatorio tecnico completo
|
|-- README.md                     # Este ficheiro
```

---

## Pre-requisitos

Antes de executar o projeto, certifique-se de que tem instalado:

- Docker Desktop (versao 24 ou superior) em execucao
- Python 3.9 ou superior
- pip (gestor de pacotes Python)
- Git

Verificar instalacoes:

```bash
docker --version
docker compose version
python --version
pip --version
```

---

## Instalacao das Dependencias Python

```bash
pip install redis faker
```

---

## Execucao Passo a Passo

### Passo 1 — Clonar o repositorio

```bash
git clone https://github.com/UR-SOUL/TRABALHO-PRATICO-2---SGBD/projeto-nosql.git
cd projeto-nosql
```

### Passo 2 — Levantar o Redis Cluster

```bash
cd docker
docker-compose up -d
```

O Docker Compose levanta 6 contentores Redis e um inicializador que configura
automaticamente o cluster com 3 masters e 3 replicas.

Aguardar aproximadamente 10 segundos e verificar o estado do cluster:

```bash
docker exec redis-master-1 redis-cli cluster info
```

Resultado esperado:

```
cluster_state:ok
cluster_slots_assigned:16384
cluster_known_nodes:6
cluster_size:3
```

Verificar a distribuicao dos nos:

```bash
docker exec redis-master-1 redis-cli cluster nodes
```

### Passo 3 — Executar o seeding (povoamento de dados)

O script de seeding insere 100.000 sessoes e 100.000 carrinhos no cluster.
A execucao demora aproximadamente 13 minutos.

```bash
# Copiar o script para dentro do contentor
docker cp scripts/seeding.py redis-master-1:/seeding.py

# Executar o seeding dentro do contentor
docker exec -it redis-master-1 python3 /seeding.py
```

Apos a conclusao, verificar o total de chaves por no:

```bash
docker exec redis-master-1 redis-cli -e --cluster call 172.20.0.11:6379 dbsize
```

Resultado esperado: aproximadamente 67.000 chaves por master
(200.001 chaves no total distribuidas pelos 3 masters).

### Passo 4 — Executar as queries avancadas

```bash
# Copiar o script para dentro do contentor
docker cp scripts/queries.py redis-master-1:/queries.py

# Executar a demonstracao dos 11 padroes de acesso
docker exec -it redis-master-1 python3 /queries.py
```

O script demonstra todas as operacoes implementadas com medicao de latencia:
criacao de sessao, listagem do carrinho, calculo de total, keep-alive, top
produtos populares, entre outras.

### Passo 5 — Executar os testes de desempenho e tolerancia a falhas

Este passo requer dois terminais abertos simultaneamente.

**Terminal 1 — Executar o benchmark:**

```bash
docker cp scripts/benchmark.py redis-master-1:/benchmark.py
docker exec -it redis-master-1 python3 /benchmark.py
```

O benchmark executa automaticamente a Parte A (latencias com 500 repeticoes).
Na Parte B, o script pausa e instrui o que executar no Terminal 2.

**Terminal 2 — Controlo do cluster (quando solicitado pelo benchmark):**

Na Fase 2 (simular falha), executar:

```bash
docker stop redis-master-2
```

Na Fase 3 (recuperacao), executar:

```bash
docker start redis-master-2
```

---

## Parar e Reiniciar o Ambiente

Parar os contentores sem apagar os dados:

```bash
cd docker
docker-compose down
```

Parar os contentores e apagar todos os volumes (reset total):

```bash
cd docker
docker-compose down -v
```

Reiniciar o cluster do zero (apos reset total):

```bash
cd docker
docker-compose up -d
```

---

## Topologia do Cluster

```
Masters                    Replicas
---------                  ----------
172.20.0.11:6379  <-----   172.20.0.15:6379
  slots: 0-5460

172.20.0.12:6379  <-----   172.20.0.16:6379
  slots: 5461-10922

172.20.0.13:6379  <-----   172.20.0.14:6379
  slots: 10923-16383
```

Cada master e responsavel por aproximadamente 1/3 dos 16.384 hash slots.
Cada master tem uma replica que recebe as escritas de forma assincrona e
e promovida automaticamente a master em caso de falha.

---

## Estruturas de Dados Redis

| Chave                        | Tipo        | Descricao                              |
|------------------------------|-------------|----------------------------------------|
| `session:{session_id}`       | HASH        | Dados da sessao do utilizador          |
| `cart:{session_id}`          | HASH        | Produtos no carrinho (JSON por campo)  |
| `analytics:popular_products` | SORTED SET  | Ranking de produtos por popularidade   |

---

## Padroes de Acesso Implementados

| Operacao                      | Comando Redis         |
|-------------------------------|-----------------------|
| Criar sessao                  | HSET + EXPIRE         |
| Obter sessao                  | HGETALL               |
| Renovar TTL (Keep-Alive)      | EXPIRE x2             |
| Adicionar produto ao carrinho | HSET + ZINCRBY        |
| Remover produto               | HDEL                  |
| Atualizar quantidade          | HSET (parcial)        |
| Listar itens do carrinho      | HGETALL               |
| Esvaziar carrinho             | DEL                   |
| Calcular total                | HGETALL + agregacao   |
| Contar sessoes ativas         | SCAN (todos os nos)   |
| Top 10 produtos populares     | ZREVRANGE WITHSCORES  |

---

## Resultados do Benchmark

Latencias medidas com 500 repeticoes por operacao (execucao dentro do cluster):

| Operacao              | Min (ms) | Media (ms) | Max (ms) | P95 (ms) | P99 (ms) |
|-----------------------|----------|------------|----------|----------|----------|
| Criar sessao          | 1.107    | 3.204      | 42.049   | 9.865    | 27.838   |
| Obter sessao          | 0.439    | 1.509      | 17.873   | 9.325    | 17.105   |
| Adicionar produto     | 1.497    | 4.763      | 34.850   | 13.833   | 25.542   |
| Listar carrinho       | 0.271    | 1.567      | 28.442   | 10.433   | 16.772   |
| Calcular total        | 0.495    | 1.435      | 17.554   | 3.726    | 13.067   |
| Renovar TTL           | 1.038    | 1.865      | 11.786   | 3.393    | 6.562    |
| Esvaziar carrinho     | 0.516    | 1.030      | 11.585   | 1.942    | 6.918    |
| Top produtos          | 0.602    | 1.316      | 11.641   | 2.619    | 5.588    |

Teste de tolerancia a falhas (simulacao de falha do master-2):

| Fase         | Disponibilidade | Latencia Media |
|--------------|-----------------|----------------|
| Baseline     | 100%            | 4.55 ms        |
| Falha master | 100%            | 4.23 ms        |
| Recuperacao  | 100%            | 5.88 ms        |

---

## Notas Tecnicas

**Porque o script e executado dentro do contentor e nao no Windows:**
O Redis Cluster comunica internamente usando os IPs da rede Docker
(172.20.0.x). O Python a correr no Windows nao tem acesso direto a essa
rede interna. Ao executar o script dentro do contentor redis-master-1,
o script ja esta na mesma rede e consegue comunicar com todos os nos
do cluster sem restricoes.

**Sobre o aviso de versao do Docker Compose:**
O aviso "version is obsolete" e inofensivo e resulta da deprecacao do
campo version no Docker Compose v2+. Nao afeta o funcionamento do projeto.

**Sobre o dbsize por no:**
O comando dbsize retorna o numero de chaves apenas do no consultado,
nao do cluster inteiro. Para obter o total real, e necessario consultar
todos os masters individualmente e somar os valores, conforme demonstrado
no Passo 3.

---

## Contacto

Para questoes relacionadas com este projeto, contactar atraves do email
ursoul05@gmail.com ou do repositorio GitHub.