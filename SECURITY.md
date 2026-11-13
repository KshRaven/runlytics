# Security

Runlytics serves your training logs over HTTP. By default it listens on `localhost` only; `--bind_all` exposes it to the network, and it has no authentication or TLS yet, so put it behind a reverse proxy or VPN if you do that.

Only the latest release receives fixes.

To report a vulnerability, use [GitHub's private vulnerability reporting](https://github.com/KshRaven/runlytics/security/advisories/new) rather than a public issue. You will get a reply within a few days.
