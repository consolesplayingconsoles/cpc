# wii

Wii node — input orchestration, controller translation, Maple bus bridge.

---

## Deploy

Deployment is handled from the repo root. The deploy script vendors all Python dependencies locally and ships everything to the console over SSH — no internet access required on the Wii.

**1. Configure**

Copy the environment template and fill in your values:

```bash
cp wii/.env.sample wii/.env
```

**2. Ship**

```bash
./deploy.sh wii/.env
```

This will:
- Vendor dependencies into `vendor/` locally
- Rsync the full project to `/opt/cpc` on the Wii
- Verify the Python environment on the device

**3. Run**

SSH into the Wii and launch:

```bash
cd /opt/cpc && PYTHONPATH=vendor python3 main.py wii/.env
```

---

## Local dev

Run the UI locally without a connected Wii using the dev entrypoint:

```bash
python3 dev.py wii
```

Uses `wii/.env`