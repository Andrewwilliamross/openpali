# Single ingress/egress boundary for the OpenPali local stack.
# Built from a digest-pinned base with the committed config baked in so the
# proxy stays bind-free (wrapper requirement).
FROM ubuntu/squid:6.13-25.04_beta@sha256:3de2e64f0ca6efdac3e98557607dc0f23050037f3885016d5d5bfcf9950501b8

COPY squid.conf /etc/squid/squid.conf
