FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# 1) Base desktop + VNC + tools + noVNC stack (+ locales + fonts)
RUN apt-get update && apt-get install -y \
    xfce4 xfce4-goodies \
    x11vnc xvfb xdotool \
    imagemagick x11-apps x11-utils x11-xserver-utils \
    sudo software-properties-common \
    curl ca-certificates \
    novnc websockify python3 \
    locales tzdata dbus-x11 \
    # A more "normal" font set for realistic font fingerprints
    fonts-dejavu-core fonts-dejavu-extra \
    fonts-liberation fonts-noto-core fonts-noto-mono fonts-noto-color-emoji \
 && apt-get remove -y light-locker xfce4-screensaver xfce4-power-manager || true \
 && rm -rf /var/lib/apt/lists/*

# Generate and set a common locale (adjust to your preference)
RUN locale-gen en_US.UTF-8 && update-locale LANG=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# 2) Firefox ESR (container-friendly)
RUN add-apt-repository ppa:mozillateam/ppa -y \
 && apt-get update \
 && apt-get install -y --no-install-recommends firefox-esr \
 && update-alternatives --set x-www-browser /usr/bin/firefox-esr \
 && rm -rf /var/lib/apt/lists/*

# 2b) Enterprise policy to set Accept-Language and a few safe defaults
RUN sudo mkdir -p /usr/lib/firefox-esr/distribution /usr/lib/firefox/distribution
COPY policies.json /usr/lib/firefox-esr/distribution/policies.json
COPY policies.json /usr/lib/firefox/distribution/policies.json

# 3) Non-root user
RUN useradd -ms /bin/bash myuser && echo "myuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
USER myuser
WORKDIR /home/myuser

# 4) VNC password (default; can be overridden at runtime via VNC_PASSWORD)
RUN x11vnc -storepasswd "secret" /home/myuser/.vncpass

# 5) Copy startup script
COPY --chown=myuser:myuser start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# 6) Expose ports for VNC and noVNC
EXPOSE 5900
EXPOSE 6080

# 7) Default display for Xvfb + noVNC port (can override NOVNC_PORT at runtime)
ENV DISPLAY=:99
ENV NOVNC_PORT=6080
ENV NO_AT_BRIDGE=1

# 8) Use exec-form JSON CMD
CMD ["bash", "-lc", "/usr/local/bin/start.sh"]
