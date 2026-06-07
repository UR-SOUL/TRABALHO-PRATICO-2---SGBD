FROM redis:7.2

RUN apt-get update -qq && \
    apt-get install -y python3 python3-pip --no-install-recommends && \
    pip3 install redis faker --break-system-packages && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*