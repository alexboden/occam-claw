FROM --platform=linux/amd64 bbernhard/signal-cli-rest-api:latest

# Replace signal-cli with v0.14.0 native build which has updated
# libsignal-service-java and refactored message receive.
RUN curl -sL https://github.com/AsamK/signal-cli/releases/download/v0.14.0/signal-cli-0.14.0-Linux-native.tar.gz \
    | tar xz -C /opt/ \
    && rm -rf /opt/signal-cli-0.13.23 \
    && chmod +x /opt/signal-cli \
    && ln -sf /opt/signal-cli /usr/local/bin/signal-cli
