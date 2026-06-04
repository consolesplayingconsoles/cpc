# ps3

PS3 node — media server orchestration, homebrew launcher, fan control.

---

## Deploy

Deployment is handled from the repo root. The deploy script vendors all Python dependencies locally and ships everything to the console over SSH — no internet access required on the PS3.

**1. Configure**

Copy the environment template and fill in your values:

```bash
cp ps3/.env.sample ps3/.env
```

**2. Ship**

```bash
./deploy.sh ps3/.env
```

This will:
- Vendor dependencies into `vendor/` locally
- Rsync the full project to `/opt/cpc` on the PS3
- Verify the Python environment on the device

**3. Run**

SSH into the PS3 and launch:

```bash
cd /opt/cpc && PYTHONPATH=vendor python3 main.py ps3/.env
```

---

## Local dev

Run the UI locally without a connected PS3 using the dev entrypoint:

```bash
python3 dev.py ps3
```

Uses `ps3/.env`
