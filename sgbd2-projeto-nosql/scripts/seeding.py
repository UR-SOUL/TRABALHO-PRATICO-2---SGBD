import json
import random
import time
import uuid
from datetime import datetime

from faker import Faker
from redis.cluster import RedisCluster
from redis.cluster import ClusterNode

STARTUP_NODES = [
    ClusterNode("172.20.0.11", 6379),
    ClusterNode("172.20.0.12", 6379),
    ClusterNode("172.20.0.13", 6379),
]

SESSION_TTL       = 1800          
TOTAL_SESSIONS    = 100_000       
BATCH_SIZE        = 500           
PRODUCTS_POOL     = 500           

fake = Faker("pt_PT")             

CATEGORIES = [
    "Eletrónicos", "Vestuário", "Calçado",
    "Livros",      "Desporto",  "Casa & Jardim",
    "Beleza",      "Brinquedos","Alimentação",  "Informática"
]

def generate_product_catalog(n: int) -> list[dict]:
 
    products = []
    for i in range(1, n + 1):
        products.append({
            "product_id": f"PROD-{i:05d}",
            "name":       fake.catch_phrase(),
            "category":   random.choice(CATEGORIES),
            "price":      round(random.uniform(1.99, 999.99), 2),
            "brand":      fake.company(),
        })
    return products



def generate_session(fake: Faker) -> dict:

    return {
        "user_id":     str(uuid.uuid4()),
        "email":       fake.email(),
        "full_name":   fake.name(),
        "ip_address":  fake.ipv4(),
        "user_agent":  fake.user_agent(),
        "created_at":  datetime.utcnow().isoformat(),
        "last_active": datetime.utcnow().isoformat(),
    }



def generate_cart(products: list[dict]) -> dict:
    cart = {}
    num_items = random.randint(1, 8)
    chosen    = random.sample(products, num_items)

    for product in chosen:
        cart[product["product_id"]] = json.dumps({
            "name":     product["name"],
            "category": product["category"],
            "price":    product["price"],
            "quantity": random.randint(1, 10),
            "brand":    product["brand"],
        })
    return cart



def seed(rc: RedisCluster, products: list[dict]) -> None:

    print(f"\n{'='*60}")
    print(f"  INÍCIO DO SEEDING")
    print(f"  Total de sessões a inserir : {TOTAL_SESSIONS:,}")
    print(f"  Tamanho do lote (batch)    : {BATCH_SIZE:,}")
    print(f"  TTL das sessões            : {SESSION_TTL}s (30 min)")
    print(f"{'='*60}\n")

    start_time      = time.time()
    session_ids     = []      

    for batch_start in range(0, TOTAL_SESSIONS, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, TOTAL_SESSIONS)


        for _ in range(batch_end - batch_start):
            session_id = str(uuid.uuid4())
            session_ids.append(session_id)

  
            session_key = f"session:{session_id}"
            session_data = generate_session(fake)
            rc.hset(session_key, mapping=session_data)
            rc.expire(session_key, SESSION_TTL)

            cart_key  = f"cart:{session_id}"
            cart_data = generate_cart(products)
            rc.hset(cart_key, mapping=cart_data)
            rc.expire(cart_key, SESSION_TTL)

            for product_id in cart_data.keys():
                rc.zincrby("analytics:popular_products", 1, product_id)


        progress = (batch_end / TOTAL_SESSIONS) * 100
        elapsed  = time.time() - start_time
        rate     = batch_end / elapsed if elapsed > 0 else 0
        print(
            f"  [{progress:5.1f}%] "
            f"{batch_end:>7,} sessões inseridas | "
            f"{rate:>8.0f} registos/s | "
            f"{elapsed:>6.1f}s decorridos"
        )

    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  SEEDING CONCLUÍDO")
    print(f"  Sessões inseridas   : {TOTAL_SESSIONS:,}")
    print(f"  Carrinhos inseridos : {TOTAL_SESSIONS:,}")
    print(f"  Tempo total         : {total_time:.2f}s")
    print(f"  Taxa média          : {TOTAL_SESSIONS/total_time:,.0f} registos/s")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print("\nA conectar ao Redis Cluster...")
    rc = RedisCluster(
        startup_nodes=STARTUP_NODES,
        decode_responses=True,
        skip_full_coverage_check=True,
    )
    print(f"Conectado! Nós activos: {len(rc.get_nodes())}")

    print("\nA gerar catálogo de produtos...")
    products = generate_product_catalog(PRODUCTS_POOL)
    print(f"Catálogo gerado: {len(products):,} produtos")

    seed(rc, products)