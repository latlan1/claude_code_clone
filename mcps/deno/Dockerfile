# deno image
FROM denoland/deno:latest
# (optional) cache the needed module so container startup is faster
RUN deno cache jsr:@pydantic/mcp-run-python || true
# ENTRYPOINT ["deno"]
