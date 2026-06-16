# Собственный образ Xray-core (SOCKS5-выход для Telethon через VLESS-ноду).
# Берём ОФИЦИАЛЬНЫЙ релиз XTLS/Xray-core (а не случайный бинарь). Свежий релиз
# нужен из-за пост-квантового шифрования VLESS (mlkem768) и транспорта xhttp.
# Конфиг НЕ зашит в образ — монтируется в рантайме из k8s-секрета xray-config
# (содержит UUID ноды). Kaniko-совместимо: без BuildKit cache-mount.

FROM alpine:3.20

RUN apk add --no-cache ca-certificates unzip wget

# latest/download всегда отдаёт ассет последнего релиза — тег знать не нужно.
RUN wget -O /tmp/xray.zip \
      https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip \
    && unzip -o /tmp/xray.zip xray -d /usr/local/bin \
    && chmod +x /usr/local/bin/xray \
    && rm /tmp/xray.zip \
    && /usr/local/bin/xray version

# Конфиг монтируется сюда из секрета (key config.json).
ENTRYPOINT ["/usr/local/bin/xray", "run", "-c", "/etc/xray/config.json"]
