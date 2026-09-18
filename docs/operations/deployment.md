# LabServer Deployment & Operations Runbook

This document describes the operational procedures for deploying, maintaining, backing up, and restoring LabServer using Docker Compose on host infrastructure.

## 1. Architecture Overview

LabServer runs as a Docker Compose stack:
- **`core`**: Application and domain service holding SQLite database (`/data/labserver.db`), background tasks, and REST API. Published strictly on `127.0.0.1:18281`.
- **`web`**: UI application rendering Jinja templates, handling browser sessions, and proxying actions to Core. Published strictly on `127.0.0.1:18280`.
- **Network**: Dedicated bridge network `labserver-net` (`10.255.30.0/24`) isolating inter-container traffic.
- **Data Persistence**: Host directory `./data` bind-mounted to `/data` in `core` container, owned by UID 1000 (`labserver`).

---

## 2. First-time Deployment

### Step 1: Configuration

From the repository root or deployment directory:

```bash
cp configs/examples/.env.production.example .env
```

Generate a cryptographically random secret key:

```bash
sed -i "s/replace_with_secure_random_hex_secret/$(openssl rand -hex 32)/" .env
```

Review `.env`:
- `LABSERVER_SECRET_KEY`: Must be populated.
- `LABSERVER_TIMEZONE`: Default `Asia/Shanghai`.
- `LABSERVER_COOKIE_SECURE`: Keep `false` during loopback testing; set to `true` when placed behind HTTPS reverse proxies.
- `LABSERVER_WEB_PORT`: Default `18280`.
- `LABSERVER_CORE_PORT`: Default `18281`.

### Step 2: Build and Launch

Build the images and launch the containers:

```bash
docker compose -f ops/docker-compose.yml up -d --build
```

Migrations will automatically execute inside the `core` container entrypoint (`alembic upgrade head`).

### Step 3: Verify Health

Verify that both services report healthy:

```bash
# Core service
curl -s http://127.0.0.1:18281/healthz
# Response: {"status":"ok"}

# Web service
curl -s http://127.0.0.1:18280/healthz
# Response: {"status":"ok"}
```

---

## 3. Initial Admin Bootstrap

On initial deployment (empty database), bootstrap the first admin user:

```bash
./ops/bootstrap-admin.sh <admin_username>
```

Output:
```text
Admin user '<admin_username>' created successfully.
One-time temporary password: <generated_password>
Save this password immediately; it cannot be recovered from the database.
```

The bootstrap CLI refuses to run if an enabled administrator already exists in the database.

---

## 4. Routine Operations

### Checking Service Status

```bash
docker compose -f ops/docker-compose.yml ps
```

### Viewing Logs

```bash
# Both services
docker compose -f ops/docker-compose.yml logs -f --tail=100

# Core only
docker compose -f ops/docker-compose.yml logs -f core

# Web only
docker compose -f ops/docker-compose.yml logs -f web
```

---

## 5. Backup & Disaster Recovery

### Online Consistent Backup

Create a live, transactionally consistent snapshot of the SQLite database without stopping services:

```bash
./ops/backup.sh [optional_target_directory]
```

The script:
1. Calls SQLite `.backup` API inside the container.
2. Copies the database snapshot to `backups/labserver-backup-<timestamp>.db`.
3. Validates SQLite `PRAGMA integrity_check;` before declaring success.

### Restoring from Backup

To restore a database snapshot:

```bash
./ops/restore.sh backups/labserver-backup-<timestamp>.db [--yes]
```

The script:
1. Validates backup file integrity (`PRAGMA integrity_check`).
2. Stops `core` and `web` containers.
3. Preserves the active live database as `labserver.db.pre-restore-<timestamp>`.
4. Copies the backup file into place and removes any dangling WAL/SHM files.
5. Restarts containers and waits for health status confirmation.

---

## 6. Upgrade & Rollback Protocol

### Performing an Upgrade

1. Create a fresh backup:
   ```bash
   ./ops/backup.sh
   ```
2. Pull latest release code:
   ```bash
   git pull origin main
   ```
3. Rebuild and restart:
   ```bash
   docker compose -f ops/docker-compose.yml up -d --build
   ```
4. Run loopback smoke test:
   ```bash
   ./ops/smoke-loopback.sh
   ```

### Performing a Rollback

1. Check out previous working commit or tag:
   ```bash
   git checkout <previous_version>
   ```
2. If migrations cannot be rolled back down cleanly, restore pre-upgrade backup:
   ```bash
   ./ops/restore.sh backups/labserver-backup-<timestamp>.db --yes
   ```
3. Rebuild and launch previous version:
   ```bash
   docker compose -f ops/docker-compose.yml up -d --build
   ```
