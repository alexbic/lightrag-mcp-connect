# supercorp/supergateway:uvx (Alpine) has no git binary, so
# `uvx --from git+URL@COMMIT ...` fails at container start with
# "Git executable not found". This adds only git — the package
# itself is still installed at startup via uvx-from-git, unchanged.
FROM supercorp/supergateway:uvx
RUN apk add --no-cache git
