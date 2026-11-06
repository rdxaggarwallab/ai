# Deploying the LMS for a pilot

This needs one Linux server (or a Windows PC with Docker Desktop) with Docker, about 2 CPUs and 4 GB RAM for a class of ~50.

## 1. Settings
```bash
git clone -b claude/bot-performance-optimization-mj3rme https://github.com/rdxaggarwallab/ai.git lms
cd lms
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # run twice: JWT_SECRET_KEY, DB_PASSWORD
nano .env
```

## 2. Start
```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api flask create-admin you@institute.edu "Your Name"
```
The site is on port 80 (`WEB_PORT` in `.env`). Only nginx is reachable. The API, database and grader are internal.

## 3. HTTPS (required)
Login cookies are HTTPS-only (`COOKIE_SECURE=true`). Put HTTPS in front, for example with
[Caddy](https://caddyserver.com): `caddy reverse-proxy --from lms.yourinstitute.edu --to localhost:80`.
If you add a proxy like this in front of nginx, the client IP passes through two hops. Nginx already
forwards the IP it sees, so it works as is. Only change `TRUSTED_PROXIES` if rate limits act strangely.

Testing on a local network without HTTPS? Set `COOKIE_SECURE=false` in `.env` for the test only.

## 4. First steps in the app
1. Log in as admin. Teachers sign up as students, then you open **Users** and change their role to **teacher**.
2. The teacher creates a course and gives students its **join code**. Students sign up and join with the code.
3. TAs: give the user the **ta** role in Users, then the teacher adds them on the course page.

## 5. Backups (daily)
```bash
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U lms lms | gzip > backup-$(date +%F).sql.gz
docker run --rm -v lms_uploads:/data -v "$PWD":/out alpine tar czf /out/uploads-$(date +%F).tgz -C /data .
```
(The volume name is `<folder>_uploads`. Check with `docker volume ls`.)

## 6. Updating
```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build   # the API applies database migrations itself
```

## Notes
- The grade worker uses the host's Docker to start one sandbox container per submission. Access to the
  Docker socket is powerful, so keep the server for the LMS only.
- Rate limits are kept in memory in the single API process (1 process, 8 threads). That is fine for one server.
