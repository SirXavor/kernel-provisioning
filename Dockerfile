FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    nginx python3 python3-flask python3-yaml \
    && apt-get clean

RUN mkdir -p /var/www/html/ipxe \
    && mkdir -p /configs \
    && mkdir -p /app

# Kernel e initrd
COPY vmlinuz /var/www/html/vmlinuz
COPY initrd  /var/www/html/initrd

# Scripts iPXE
COPY ipxe/ /var/www/html/ipxe/

# Servidor dinamico
COPY server.py /app/server.py

# Configuracion nginx (sustituye la de defecto)
COPY nginx.conf /etc/nginx/sites-available/default

# Entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 80/tcp
EXPOSE 8080/tcp

CMD ["/app/entrypoint.sh"]
