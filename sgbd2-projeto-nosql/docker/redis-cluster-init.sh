echo "Aguardando os nós Redis ficarem prontos..."
sleep 5

echo "Iniciando o Redis Cluster com 3 masters e 3 réplicas..."

redis-cli --cluster create \
  172.20.0.11:6379 \
  172.20.0.12:6379 \
  172.20.0.13:6379 \
  172.20.0.14:6379 \
  172.20.0.15:6379 \
  172.20.0.16:6379 \
  --cluster-replicas 1 \
  --cluster-yes

if [ $? -eq 0 ]; then
  echo "Cluster iniciado com sucesso!"
  echo ""
  echo "Estado do cluster:"
  redis-cli -h 172.20.0.11 -p 6379 cluster info
  echo ""
  echo "Nós do cluster:"
  redis-cli -h 172.20.0.11 -p 6379 cluster nodes
else
  echo "Erro ao iniciar o cluster. Verifica se todos os contentores estão em execução."
  exit 1
fi