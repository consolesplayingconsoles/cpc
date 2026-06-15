# Pluto

Network dashboard for consolesplayingconsoles. Real-time node topology, live ping status, and console management.

---

## Run (dev)

```bash
# first time only
cp pluto/.env.sample pluto/.env
(cd pluto && yarn install)
```

```bash
# from the repo root — boots the dev env: API (:7700) + Vite (:5173) + Swagger UI (:7800)
./start-pluto.sh           # --api or --web to start just one half
```

## Deploy (prod)

`./deploy.sh pluto/.env` builds the SPA and ships the API + `dist/` + `config/` to the
host, where `pluto/serve.sh` (under systemd) serves it. The dev-only tooling
(`start-pluto.sh`, `tools/swagger.py`) is never deployed.

Or just start pluto, click on the Pluto bubble in the diagram and hit the deploy button.

If a node client exists, that node will also have a deploy button to deploy the client.