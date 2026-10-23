# Deploying on Mikrus (lucjan266)

Layout follows the other apps on this server: container on `127.0.0.1:51xx`, Nginx on `[::]:50xx`, free subdomain from the panel. Both IPv4 service ports (20266, 30266) are already used by other apps and are not touched.

| What | Where |
|---|---|
| Source (git checkout) | `/root/MCPAPPS/ubiblio/src` |
| Database, secret and federation keys | `/root/MCPAPPS/ubiblio/config` |
| Backups made by the app, CSV exports | `/root/MCPAPPS/ubiblio/export` |
| Cover images, ebook files | `/root/MCPAPPS/ubiblio/bookImages`, `/root/MCPAPPS/ubiblio/eBooks` |
| Secrets for compose (`GEMINI_API_KEY`, admin password on first start) | `/root/MCPAPPS/ubiblio/ubiblio.env` (chmod 600) |
| Nginx vhost | `/etc/nginx/sites-available/ubiblio.conf` (`[::]:5005` -> `127.0.0.1:5105`) |
| Nightly backup | `/etc/cron.d/ubiblio-backup` -> `deploy/backup.sh` -> `/backup/DB/ubiblio-*.gz` |
| URL | https://ubiblio.byst.re/ (free subdomain -> `[IPv6]:5005`, HTTPS by Mikrus) |

## First deployment

```sh
mkdir -p /root/MCPAPPS/ubiblio/{config,export,bookImages,eBooks}
git clone <repo> /root/MCPAPPS/ubiblio/src            # or: clone upstream + git pull from a bundle
cd /root/MCPAPPS/ubiblio/src
umask 077; printf 'CREATE_ADMIN_USER=true\nADMIN_USERNAME=admin\nADMIN_PASSWORD=%s\n' "$(openssl rand -base64 18)" > ../ubiblio.env
docker compose -f deploy/docker-compose.yml --env-file ../ubiblio.env up -d --build
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5105/user-setup/   # creates the admin once
sed -i 's/^CREATE_ADMIN_USER=true/CREATE_ADMIN_USER=false/; /^ADMIN_PASSWORD=/d' ../ubiblio.env   # after noting the password
docker compose -f deploy/docker-compose.yml --env-file ../ubiblio.env up -d
cp deploy/nginx-ubiblio.conf /etc/nginx/sites-available/ubiblio.conf
ln -s /etc/nginx/sites-available/ubiblio.conf /etc/nginx/sites-enabled/ubiblio.conf
nginx -t && nginx -s reload
install -m 644 deploy/ubiblio-backup.cron /etc/cron.d/ubiblio-backup; chmod +x deploy/backup.sh
```

Then add the free subdomain `ubiblio.byst.re` -> port 5005 in the panel.

## Update

```sh
cd /root/MCPAPPS/ubiblio/src && git pull
docker compose -f deploy/docker-compose.yml --env-file ../ubiblio.env up -d --build
```

The app makes `export/preUpdateExport*.sql` itself before a database migration (open `/` as admin after an update).

## Start / stop / health

- start/restart: `docker compose -f deploy/docker-compose.yml --env-file ../ubiblio.env up -d` / `docker restart ubiblio`
- stop: `docker stop ubiblio`
- health: `curl -I http://127.0.0.1:5105/` and `curl -I https://ubiblio.byst.re/`
- memory: `docker stats --no-stream ubiblio`
- one worker only: import jobs keep their state in process memory.
