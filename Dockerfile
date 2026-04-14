FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    nginx \
    python3 \
    python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/www/html/ipxe \
    && mkdir -p /var/www/html/content \
    && mkdir -p /configs \
    && mkdir -p /app

COPY vmlinuz /var/www/html/vmlinuz
COPY initrd /var/www/html/initrd
COPY app/ /app/
RUN pip3 install --break-system-packages -r /app/requirements.txt

COPY nginx.conf /etc/nginx/sites-available/default
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 80/tcp
EXPOSE 8080/tcp

CMD ["/app/entrypoint.sh"]