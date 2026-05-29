import json
import time
import uuid
from datetime import datetime
from redis.cluster import ClusterNode, RedisCluster

STARTUP_NODES = [
    ClusterNode("172.20.0.11", 6379),
    ClusterNode("172.20.0.12", 6379),
    ClusterNode("172.20.0.13", 6379),
]
SESSION_TTL = 1800  # 30 minutos

def get_connection() -> RedisCluster:
    return RedisCluster(
        startup_nodes=STARTUP_NODES,
        decode_responses=True,
        skip_full_coverage_check=True,
    )

def qa01_criar_sessao(rc: RedisCluster, user_data: dict) -> str:
    session_id   = str(uuid.uuid4())
    session_key  = f"session:{session_id}"
    cart_key     = f"cart:{session_id}"

    session_data = {
        "user_id":     user_data.get("user_id", str(uuid.uuid4())),
        "email":       user_data.get("email", ""),
        "full_name":   user_data.get("full_name", ""),
        "ip_address":  user_data.get("ip_address", ""),
        "created_at":  datetime.utcnow().isoformat(),
        "last_active": datetime.utcnow().isoformat(),
    }

    rc.hset(session_key, mapping=session_data)
    rc.expire(session_key, SESSION_TTL)
    rc.expire(cart_key, SESSION_TTL)

    return session_id


def qa02_obter_sessao(rc: RedisCluster, session_id: str) -> dict | None:
    session_key = f"session:{session_id}"
    data = rc.hgetall(session_key)
    return data if data else None


def qa03_renovar_ttl(rc: RedisCluster, session_id: str) -> bool:
    session_key = f"session:{session_id}"
    cart_key    = f"cart:{session_id}"

    rc.hset(session_key, "last_active", datetime.utcnow().isoformat())
    r1 = rc.expire(session_key, SESSION_TTL)
    r2 = rc.expire(cart_key,    SESSION_TTL)

    return bool(r1 and r2)

def qa05_adicionar_produto(
    rc: RedisCluster,
    session_id: str,
    product: dict
) -> int:
    cart_key   = f"cart:{session_id}"
    product_id = product["product_id"]

    existing = rc.hget(cart_key, product_id)
    if existing:
        item = json.loads(existing)
        item["quantity"] += product.get("quantity", 1)
    else:
        item = {
            "name":     product["name"],
            "category": product.get("category", ""),
            "price":    product["price"],
            "quantity": product.get("quantity", 1),
            "brand":    product.get("brand", ""),
        }

    rc.hset(cart_key, product_id, json.dumps(item))
    rc.expire(cart_key, SESSION_TTL)

    rc.zincrby("analytics:popular_products", 1, product_id)
    qa03_renovar_ttl(rc, session_id)

    return item["quantity"]


def qa06_remover_produto(
    rc: RedisCluster,
    session_id: str,
    product_id: str
) -> bool:

    cart_key = f"cart:{session_id}"
    result   = rc.hdel(cart_key, product_id)
    qa03_renovar_ttl(rc, session_id)
    return bool(result)


def qa07_atualizar_quantidade(
    rc: RedisCluster,
    session_id: str,
    product_id: str,
    nova_quantidade: int
) -> bool:

    cart_key = f"cart:{session_id}"
    existing = rc.hget(cart_key, product_id)

    if not existing:
        return False

    item = json.loads(existing)
    item["quantity"] = nova_quantidade
    rc.hset(cart_key, product_id, json.dumps(item))
    qa03_renovar_ttl(rc, session_id)
    return True


def qa08_listar_carrinho(
    rc: RedisCluster,
    session_id: str
) -> list[dict]:

    cart_key = f"cart:{session_id}"
    raw      = rc.hgetall(cart_key)

    items = []
    for product_id, json_data in raw.items():
        item = json.loads(json_data)
        item["product_id"] = product_id
        items.append(item)

    return items


def qa09_esvaziar_carrinho(
    rc: RedisCluster,
    session_id: str
) -> bool:

    cart_key = f"cart:{session_id}"
    result   = rc.delete(cart_key)
    return bool(result)


def qa10_calcular_total(
    rc: RedisCluster,
    session_id: str
) -> dict:

    items      = qa08_listar_carrinho(rc, session_id)
    total      = sum(i["price"] * i["quantity"] for i in items)
    num_items  = sum(i["quantity"] for i in items)

    return {
        "session_id":    session_id,
        "total_price":   round(total, 2),
        "total_items":   num_items,
        "total_products": len(items),
    }

def qa11_contar_sessoes_ativas(rc: RedisCluster) -> dict:
    total_sessions = 0
    total_carts    = 0

    for node in rc.get_primaries():
        node_client = rc.get_redis_connection(node)
        cursor      = 0

        while True:
            cursor, keys = node_client.scan(
                cursor, match="session:*", count=1000
            )
            total_sessions += len(keys)
            if cursor == 0:
                break

        cursor = 0
        while True:
            cursor, keys = node_client.scan(
                cursor, match="cart:*", count=1000
            )
            total_carts += len(keys)
            if cursor == 0:
                break

    return {
        "sessoes_ativas":   total_sessions,
        "carrinhos_ativos": total_carts,
    }


def qa12_top_produtos(rc: RedisCluster, top_n: int = 10) -> list[dict]:
    results = rc.zrevrange(
        "analytics:popular_products",
        0, top_n - 1,
        withscores=True
    )
    return [
        {"product_id": pid, "total_adicionado": int(score)}
        for pid, score in results
    ]


def medir_tempo(label: str, func, *args) -> any:
    inicio    = time.perf_counter()
    resultado = func(*args)
    fim       = time.perf_counter()
    latencia  = (fim - inicio) * 1000
    print(f"  {label:<45} {latencia:>8.3f} ms")
    return resultado


def executar_demonstracao(rc: RedisCluster) -> None:
    print("\n" + "="*60)
    print("  DEMONSTRAÇÃO DAS OPERAÇÕES AVANÇADAS")
    print("="*60)

    print("\nQA-01 — Criar sessão de utilizador")
    user_data = {
        "user_id":   str(uuid.uuid4()),
        "email":     "pedro.bengui@exemplo.pt",
        "full_name": "Pedro Bengui",
        "ip_address": "192.168.1.100",
    }
    session_id = medir_tempo(
        "HSET session + EXPIRE (criar sessão)",
        qa01_criar_sessao, rc, user_data
    )
    print(f"     session_id: {session_id}")

    print("\nQA-02 — Obter dados da sessão")
    sessao = medir_tempo(
        "HGETALL session:{id}",
        qa02_obter_sessao, rc, session_id
    )
    for k, v in sessao.items():
        print(f"     {k}: {v}")

    print("\nQA-05 — Adicionar produtos ao carrinho")
    produtos_teste = [
        {"product_id": "PROD-00001", "name": "Laptop Pro 15",
         "price": 1299.99, "category": "Informática",
         "brand": "TechBrand", "quantity": 1},
        {"product_id": "PROD-00042", "name": "Rato Wireless",
         "price": 29.99, "category": "Informática",
         "brand": "PeriphBrand", "quantity": 2},
        {"product_id": "PROD-00100", "name": "Mochila Executiva",
         "price": 89.99, "category": "Vestuário",
         "brand": "BagBrand", "quantity": 1},
    ]
    for p in produtos_teste:
        qty = medir_tempo(
            f"HSET cart + ZINCRBY ({p['name'][:25]})",
            qa05_adicionar_produto, rc, session_id, p
        )
        print(f"     Quantidade no carrinho: {qty}")

    print("\nQA-08 — Listar todos os itens do carrinho")
    items = medir_tempo(
        "HGETALL cart:{session_id}",
        qa08_listar_carrinho, rc, session_id
    )
    for item in items:
        print(
            f"     [{item['product_id']}] "
            f"{item['name'][:30]:<30} "
            f"x{item['quantity']}  "
            f"€{item['price']:.2f}"
        )

    print("\nQA-10 — Calcular total do carrinho")
    total = medir_tempo(
        "Agregação price * quantity (total)",
        qa10_calcular_total, rc, session_id
    )
    print(f"     Total produtos distintos : {total['total_products']}")
    print(f"     Total unidades           : {total['total_items']}")
    print(f"     Total a pagar            : €{total['total_price']:.2f}")


    print("\nQA-07 — Actualizar quantidade de produto")
    ok = medir_tempo(
        "HSET parcial (update quantity em JSON)",
        qa07_atualizar_quantidade,
        rc, session_id, "PROD-00042", 5
    )
    print(f"     Actualização bem-sucedida: {ok}")


    print("\nQA-03 — Renovar TTL (Keep-Alive)")
    ttl_antes = rc.ttl(f"session:{session_id}")
    renovado  = medir_tempo(
        "EXPIRE session + EXPIRE cart (keep-alive)",
        qa03_renovar_ttl, rc, session_id
    )
    ttl_depois = rc.ttl(f"session:{session_id}")
    print(f"     TTL antes  : {ttl_antes}s")
    print(f"     TTL depois : {ttl_depois}s")
    print(f"     Renovado   : {renovado}")

    print("\nQA-06 — Remover produto do carrinho")
    removido = medir_tempo(
        "HDEL cart:{id} {product_id}",
        qa06_remover_produto, rc, session_id, "PROD-00100"
    )
    print(f"     Produto PROD-00100 removido: {removido}")


    print("\nQA-09 — Esvaziar carrinho (Clear Cart)")
    esvaziado = medir_tempo(
        "DEL cart:{session_id} (atómico)",
        qa09_esvaziar_carrinho, rc, session_id
    )
    print(f"     Carrinho esvaziado: {esvaziado}")
    itens_apos = qa08_listar_carrinho(rc, session_id)
    print(f"     Itens restantes   : {len(itens_apos)}")

    print("\nQA-11 — Contar sessões e carrinhos activos")
    stats = medir_tempo(
        "SCAN session:* + SCAN cart:* (todos os nós)",
        qa11_contar_sessoes_ativas, rc
    )
    print(f"     Sessões activas   : {stats['sessoes_ativas']:,}")
    print(f"     Carrinhos activos : {stats['carrinhos_ativos']:,}")

    print("\nQA-12 — Top 10 produtos mais populares")
    top = medir_tempo(
        "ZREVRANGE analytics:popular_products (top 10)",
        qa12_top_produtos, rc, 10
    )
    print(f"     {'Produto':<15} {'Vezes adicionado':>20}")
    print(f"     {'-'*35}")
    for i, p in enumerate(top, 1):
        print(
            f"     {i:>2}. {p['product_id']:<12} "
            f"{p['total_adicionado']:>15,}x"
        )

    print("\n" + "="*60)
    print("  DEMONSTRAÇÃO CONCLUÍDA")
    print("="*60 + "\n")



if __name__ == "__main__":
    print("\nA conectar ao Redis Cluster...")
    rc = get_connection()
    print(f"Conectado! Nós activos: {len(rc.get_nodes())}")
    executar_demonstracao(rc)