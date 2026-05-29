import json
import statistics
import time
import uuid
from datetime import datetime

from redis.cluster import ClusterNode, RedisCluster
from redis.exceptions import RedisClusterException, RedisError

STARTUP_NODES = [
    ClusterNode("172.20.0.11", 6379),
    ClusterNode("172.20.0.12", 6379),
    ClusterNode("172.20.0.13", 6379),
]
SESSION_TTL = 1800
REPETICOES  = 500


def get_connection() -> RedisCluster:
    return RedisCluster(
        startup_nodes=STARTUP_NODES,
        decode_responses=True,
        skip_full_coverage_check=True,
    )


def calcular_estatisticas(latencias: list[float]) -> dict:
    ordenadas = sorted(latencias)
    n         = len(ordenadas)
    return {
        "min":   round(min(ordenadas), 3),
        "max":   round(max(ordenadas), 3),
        "media": round(statistics.mean(ordenadas), 3),
        "p95":   round(ordenadas[int(n * 0.95)], 3),
        "p99":   round(ordenadas[int(n * 0.99)], 3),
    }


def imprimir_tabela_stats(resultados: dict) -> None:
    col_op  = 42
    col_num = 10
    header = (
        f"  {'Operação':<{col_op}} "
        f"{'Mín(ms)':>{col_num}} "
        f"{'Méd(ms)':>{col_num}} "
        f"{'Máx(ms)':>{col_num}} "
        f"{'P95(ms)':>{col_num}} "
        f"{'P99(ms)':>{col_num}}"
    )
    separador = "  " + "-" * (col_op + col_num * 5 + 10)
    print(header)
    print(separador)
    for label, stats in resultados.items():
        print(
            f"  {label:<{col_op}} "
            f"{stats['min']:>{col_num}} "
            f"{stats['media']:>{col_num}} "
            f"{stats['max']:>{col_num}} "
            f"{stats['p95']:>{col_num}} "
            f"{stats['p99']:>{col_num}}"
        )


def benchmark_criar_sessao(rc, n):
    latencias, session_ids = [], []
    for _ in range(n):
        sid = str(uuid.uuid4())
        t0  = time.perf_counter()
        rc.hset(f"session:{sid}", mapping={
            "user_id":     str(uuid.uuid4()),
            "email":       "bench@teste.pt",
            "created_at":  datetime.utcnow().isoformat(),
            "last_active": datetime.utcnow().isoformat(),
        })
        rc.expire(f"session:{sid}", SESSION_TTL)
        latencias.append((time.perf_counter() - t0) * 1000)
        session_ids.append(sid)
    return calcular_estatisticas(latencias), session_ids


def benchmark_hgetall(rc, session_ids, n):
    latencias = []
    for sid in session_ids[:n]:
        t0 = time.perf_counter()
        rc.hgetall(f"session:{sid}")
        latencias.append((time.perf_counter() - t0) * 1000)
    return calcular_estatisticas(latencias)


def benchmark_adicionar_produto(rc, session_ids, n):
    latencias = []
    produto   = json.dumps({
        "name": "Produto Benchmark", "price": 99.99,
        "quantity": 1, "category": "Teste", "brand": "Bench"
    })
    for sid in session_ids[:n]:
        t0 = time.perf_counter()
        rc.hset(f"cart:{sid}", "PROD-BENCH", produto)
        rc.expire(f"cart:{sid}", SESSION_TTL)
        rc.zincrby("analytics:popular_products", 1, "PROD-BENCH")
        latencias.append((time.perf_counter() - t0) * 1000)
    return calcular_estatisticas(latencias)


def benchmark_listar_carrinho(rc, session_ids, n):
    latencias = []
    for sid in session_ids[:n]:
        t0 = time.perf_counter()
        rc.hgetall(f"cart:{sid}")
        latencias.append((time.perf_counter() - t0) * 1000)
    return calcular_estatisticas(latencias)


def benchmark_calcular_total(rc, session_ids, n):
    latencias = []
    for sid in session_ids[:n]:
        t0  = time.perf_counter()
        raw = rc.hgetall(f"cart:{sid}")
        sum(
            json.loads(v)["price"] * json.loads(v)["quantity"]
            for v in raw.values()
        )
        latencias.append((time.perf_counter() - t0) * 1000)
    return calcular_estatisticas(latencias)


def benchmark_renovar_ttl(rc, session_ids, n):
    latencias = []
    for sid in session_ids[:n]:
        t0 = time.perf_counter()
        rc.expire(f"session:{sid}", SESSION_TTL)
        rc.expire(f"cart:{sid}", SESSION_TTL)
        latencias.append((time.perf_counter() - t0) * 1000)
    return calcular_estatisticas(latencias)


def benchmark_esvaziar_carrinho(rc, session_ids, n):
    latencias = []
    for sid in session_ids[:n]:
        t0 = time.perf_counter()
        rc.delete(f"cart:{sid}")
        latencias.append((time.perf_counter() - t0) * 1000)
    return calcular_estatisticas(latencias)


def benchmark_top_produtos(rc, n):
    latencias = []
    for _ in range(n):
        t0 = time.perf_counter()
        rc.zrevrange("analytics:popular_products", 0, 9, withscores=True)
        latencias.append((time.perf_counter() - t0) * 1000)
    return calcular_estatisticas(latencias)


def executar_parte_a(rc) -> None:
    print("\n" + "="*75)
    print("  PARTE A — BENCHMARK DE LATÊNCIAS")
    print(f"  Repetições por operação: {REPETICOES:,}")
    print("="*75)

    resultados = {}

    print(f"\nA medir QA-01 Criar sessão ({REPETICOES}x)...")
    stats, session_ids = benchmark_criar_sessao(rc, REPETICOES)
    resultados["QA-01 Criar sessão (HSET+EXPIRE)"] = stats

    print(f" A medir QA-02 Obter sessão ({REPETICOES}x)...")
    stats = benchmark_hgetall(rc, session_ids, REPETICOES)
    resultados["QA-02 Obter sessão (HGETALL)"] = stats

    print(f" A medir QA-05 Adicionar produto ({REPETICOES}x)...")
    stats = benchmark_adicionar_produto(rc, session_ids, REPETICOES)
    resultados["QA-05 Adicionar produto (HSET+ZINCRBY)"] = stats

    print(f"A medir QA-08 Listar carrinho ({REPETICOES}x)...")
    stats = benchmark_listar_carrinho(rc, session_ids, REPETICOES)
    resultados["QA-08 Listar carrinho (HGETALL)"] = stats

    print(f"A medir QA-10 Calcular total ({REPETICOES}x)...")
    stats = benchmark_calcular_total(rc, session_ids, REPETICOES)
    resultados["QA-10 Calcular total (HGETALL+agregação)"] = stats

    print(f"A medir QA-03 Renovar TTL ({REPETICOES}x)...")
    stats = benchmark_renovar_ttl(rc, session_ids, REPETICOES)
    resultados["QA-03 Renovar TTL (EXPIRE×2)"] = stats

    print(f" A medir QA-09 Esvaziar carrinho ({REPETICOES}x)...")
    stats = benchmark_esvaziar_carrinho(rc, session_ids, REPETICOES)
    resultados["QA-09 Esvaziar carrinho (DEL)"] = stats

    print(f" A medir QA-12 Top produtos ({REPETICOES}x)...")
    stats = benchmark_top_produtos(rc, REPETICOES)
    resultados["QA-12 Top produtos (ZREVRANGE)"] = stats

    print("\n")
    imprimir_tabela_stats(resultados)
    print("\n Parte A concluída!")

def medir_latencia_operacao(rc) -> float | None:
    try:
        sid = str(uuid.uuid4())
        t0  = time.perf_counter()
        rc.hset(f"session:{sid}", mapping={"teste": "cap"})
        rc.expire(f"session:{sid}", 10)
        return (time.perf_counter() - t0) * 1000
    except (RedisClusterException, RedisError):
        return None


def monitorizar_cluster(rc, duracao: int, label: str) -> list:
    registos = []
    print(f"\n  {'Seg':>4}  {'Estado':<12} {'Latência':>10}")
    print(f"  {'-'*35}")
    for i in range(duracao):
        latencia = medir_latencia_operacao(rc)
        if latencia is not None:
            estado = "OK"
            obs    = f"{latencia:.2f} ms"
        else:
            estado = "FALHA"
            obs    = "Operação falhou"
        print(f"  {i+1:>4}s  {estado:<12} {obs:>10}")
        registos.append({
            "segundo":    i + 1,
            "fase":       label,
            "latencia":   latencia,
            "disponivel": latencia is not None,
        })
        time.sleep(1)
    return registos


def executar_parte_b() -> None:
    print("\n" + "="*75)
    print("  PARTE B — TOLERÂNCIA A FALHAS (TEOREMA CAP NA PRÁTICA)")
    print("="*75)

    todos_registos = []

    print("\n FASE 1 — Baseline (cluster normal)")
    print("  Não faças nada. Apenas observa.")
    input("\n Prime ENTER para iniciar monitorização baseline...")
    rc       = get_connection()
    registos = monitorizar_cluster(rc, 10, "baseline")
    todos_registos.extend(registos)
    disponiveis = [r for r in registos if r["disponivel"]]
    lat_base    = statistics.mean(r["latencia"] for r in disponiveis)
    print(f"\n  Latência média baseline : {lat_base:.2f} ms")
    print(f"  Disponibilidade         : {len(disponiveis)}/10")

    print("\n FASE 2 — Simular falha do redis-master-2")
    print("    No Terminal 2 executa:                     ")
    print("    docker stop redis-master-2                 ")
    input("\n Depois de executar o comando, prime ENTER aqui...")
    print("\n Monitorização durante falha (20 segundos)...")
    rc2      = get_connection()
    registos = monitorizar_cluster(rc2, 20, "falha")
    todos_registos.extend(registos)
    falhas      = [r for r in registos if not r["disponivel"]]
    recuperados = [r for r in registos if r["disponivel"]]
    print(f"\n  Operações falhadas  : {len(falhas)}/20")
    print(f"  Operações com êxito : {len(recuperados)}/20")
    if recuperados:
        lat_falha = statistics.mean(r["latencia"] for r in recuperados)
        print(f"  Latência média      : {lat_falha:.2f} ms")
        print(f"  Impacto vs baseline : +{lat_falha - lat_base:.2f} ms")

    print("\n FASE 3 — Recuperação do cluster")
    print("    No Terminal 2 executa:                     ")
    print("    docker start redis-master-2                ")
    input("\n Depois de executar o comando, prime ENTER aqui...")
    print("  Aguardando resincronização (10 segundos)...")
    time.sleep(10)
    print("\n  Monitorização após recuperação (10 segundos)...")
    rc3      = get_connection()
    registos = monitorizar_cluster(rc3, 10, "recuperacao")
    todos_registos.extend(registos)
    disponiveis_rec = [r for r in registos if r["disponivel"]]
    if disponiveis_rec:
        lat_rec = statistics.mean(r["latencia"] for r in disponiveis_rec)
        print(f"\n  Latência pós-recuperação : {lat_rec:.2f} ms")
        print(f"  Comparação com baseline  : +{lat_rec - lat_base:.2f} ms")

    print("\n" + "="*75)
    print("  RESUMO — ANÁLISE CAP")
    print("="*75)
    fases = ["baseline", "falha", "recuperacao"]
    for fase in fases:
        regs = [r for r in todos_registos if r["fase"] == fase]
        disp = [r for r in regs if r["disponivel"]]
        pct  = (len(disp) / len(regs)) * 100 if regs else 0
        lat  = statistics.mean(r["latencia"] for r in disp) if disp else 0
        print(
            f"  {fase.upper():<15} "
            f"Disponibilidade: {pct:>6.1f}%  "
            f"Latência média: {lat:>8.2f} ms"
        )
    print("\n CONCLUSÃO CAP:")
    print("  Redis Cluster prioriza DISPONIBILIDADE (A) e")
    print("  TOLERÂNCIA A PARTIÇÕES (P) sobre Consistência (C).")
    print("  Durante a falha, a réplica foi promovida a master,")
    print("  mantendo o sistema operacional (consistência eventual).")
    print("="*75 + "\n")

if __name__ == "__main__":
    print("\nA conectar ao Redis Cluster...")
    rc = get_connection()
    print(f"Conectado! Nós activos: {len(rc.get_nodes())}")

    executar_parte_a(rc)
    executar_parte_b()