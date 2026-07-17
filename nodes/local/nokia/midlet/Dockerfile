FROM eclipse-temurin:8-jdk

# preverify from WTK is a 32-bit x86 ELF binary -> need i386 runtime libs
RUN dpkg --add-architecture i386 && apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates \
        libc6:i386 libstdc++6:i386 zlib1g:i386 \
        libxt6:i386 libx11-6:i386 libxext6:i386 && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/vipaoL/j2me-build-tools /tools

WORKDIR /work
